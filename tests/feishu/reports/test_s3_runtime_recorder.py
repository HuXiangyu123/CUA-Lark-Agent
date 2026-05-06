import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui_agents.feishu.reports.s3_runtime_recorder import S3RuntimeRecorder


class TestS3RuntimeRecorder(unittest.TestCase):
    def _vc_observation(self, filename: str) -> dict:
        return {"image_path": str(Path("tests/fixtures/vc") / filename)}

    def _unknown_live_observation(self) -> dict:
        return {"ocr_text": "Qs\nSHMESREWN"}

    def test_records_agent_s3_runtime_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("发起视频会议并验证进入成功")
            recorder.record_observation(1, {"screenshot": b"png"})
            recorder.record_action(
                1,
                "import pyautogui\npyautogui.click(10, 20)\n",
                "executed",
            )
            paths = recorder.finalize(
                "completed",
                final_observation=self._vc_observation("正在会议的页面.png"),
            )

            self.assertIsNotNone(paths)
            assert paths is not None
            summary = json.loads(Path(paths["summary"]).read_text("utf-8"))
            self.assertEqual(summary["intent"], "agent_s3_feishu")
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["product"], "vc")
            self.assertEqual(summary["task_id"], "agentic_vc_start_meeting")
            self.assertGreaterEqual(summary["passed_steps"], 1)
            self.assertEqual(summary["failed_steps"], 0)
            self.assertEqual(summary["assertions"][0]["name"], "vc_meeting_active")
            self.assertTrue(summary["assertions"][0]["passed"])
            self.assertTrue(runtime["screenshots"])
            self.assertTrue(Path(runtime["screenshots"][0]).exists())
            self.assertIn("pyautogui.click", Path(paths["actions"]).read_text("utf-8"))
            self.assertTrue(Path(paths["semantic_trace"]).exists())
            self.assertTrue(Path(paths["replay_draft"]).exists())

    def test_start_creates_incremental_artifacts_before_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("打开消息")
            run_dir = Path(tmpdir) / runtime["run_id"]

            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "report.md").exists())
            self.assertTrue((run_dir / "actions.jsonl").exists())
            self.assertTrue((run_dir / "runtime_state.json").exists())
            self.assertTrue((run_dir / "runtime_stdout.log").exists())
            self.assertTrue((run_dir / "replay_draft.md").exists())
            self.assertEqual(recorder.run_dir(), str(run_dir))
            self.assertEqual(
                recorder.runtime_stdout_path(),
                str(run_dir / "runtime_stdout.log"),
            )

    def test_record_action_refreshes_actions_jsonl_during_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("打开消息")
            recorder.record_action(1, "agent.wait(1)", "wait")
            run_dir = Path(tmpdir) / runtime["run_id"]
            actions = (run_dir / "actions.jsonl").read_text(encoding="utf-8")
            summary = json.loads((run_dir / "summary.json").read_text("utf-8"))

            self.assertIn('"action": "wait"', actions)
            self.assertEqual(summary["artifact_write_reason"], "action_001")

    def test_record_action_syncs_artifacts_once_per_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)
            recorder.start("打开消息")

            with patch.object(
                recorder,
                "_sync_artifacts",
                wraps=recorder._sync_artifacts,
            ) as sync_mock:
                recorder.record_action(1, "agent.wait(1)", "wait")

            self.assertEqual(sync_mock.call_count, 1)
            self.assertEqual(sync_mock.call_args.args[0], "action_001")

    def test_record_observation_uses_lightweight_live_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)
            runtime = recorder.start("打开日历主页")

            with patch.object(
                recorder.report_builder,
                "build_markdown",
                wraps=recorder.report_builder.build_markdown,
            ) as markdown_mock:
                recorder.record_observation(1, {"screenshot": b"png"})

            run_dir = Path(tmpdir) / runtime["run_id"]
            self.assertEqual(markdown_mock.call_count, 0)
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "runtime_state.json").exists())
            summary = json.loads((run_dir / "summary.json").read_text("utf-8"))
            self.assertEqual(summary["artifact_write_reason"], "observation_001")

    def test_record_action_derives_semantic_step_from_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("发起视频会议并验证进入会议中页面")
            recorder.record_observation(
                1,
                {"ocr_text": "视频会议\n发起会议\n加入会议\n历史记录"},
            )
            recorder.record_action(
                1,
                "agent.feishu_vc_click_start_card()",
                "executed",
            )
            paths = recorder.finalize("completed")

            self.assertIsNotNone(paths)
            assert paths is not None
            self.assertEqual(runtime["semantic_steps"][0]["page_type"], "vc_home")
            self.assertIn(
                "start_card", runtime["semantic_steps"][0]["visible_controls"]
            )
            trace = json.loads(Path(paths["semantic_trace"]).read_text("utf-8"))
            replay = Path(paths["replay_draft"]).read_text("utf-8")
            serialized = json.dumps(trace, ensure_ascii=False)
            self.assertIn("click visible interface control", serialized)
            self.assertNotIn("feishu_vc_click_start_card", serialized)
            self.assertNotIn("pyautogui", replay)

    def test_marks_runtime_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            recorder.start("打开消息")
            recorder.record_action(
                1,
                "raise RuntimeError('boom')",
                "failed",
                "RuntimeError('boom')",
            )
            paths = recorder.finalize()

            self.assertIsNotNone(paths)
            assert paths is not None
            summary = json.loads(Path(paths["summary"]).read_text("utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["failed_steps"], 1)
            self.assertEqual(summary["failure_type"], "runtime")

    def test_record_action_persists_reflection_for_process_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("打开消息")
            recorder.record_action(
                1,
                "agent.wait(1)",
                "wait",
                reflection="previous click did not settle; wait before retry",
            )
            paths = recorder.finalize("completed")

            self.assertIsNotNone(paths)
            assert paths is not None
            summary = json.loads(Path(paths["summary"]).read_text("utf-8"))
            self.assertEqual(summary["reflection_count"], 1)
            self.assertEqual(
                runtime["reflections"][0],
                "previous click did not settle; wait before retry",
            )
            self.assertEqual(
                runtime["action_logs"][0]["reflection"],
                "previous click did not settle; wait before retry",
            )

    def test_finalize_writes_artifact_error_when_report_generation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("打开消息")

            def _raise(*_args, **_kwargs):
                raise RuntimeError("summary boom")

            recorder.report_builder.build_summary = _raise
            paths = recorder.finalize("failed", failure_reason="forced failure")
            run_dir = Path(tmpdir) / runtime["run_id"]

            self.assertIsNotNone(paths)
            self.assertTrue((run_dir / "artifact_error.txt").exists())
            self.assertIn(
                "summary boom",
                (run_dir / "artifact_error.txt").read_text(encoding="utf-8"),
            )
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "replay_draft.md").exists())

    def test_final_verification_can_flip_done_run_to_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            recorder.start("发起视频会议并验证进入成功")
            recorder.record_action(
                1,
                "agent.done()",
                "done",
            )
            paths = recorder.finalize(
                "completed",
                final_observation=self._vc_observation("会议主页面.png"),
            )

            self.assertIsNotNone(paths)
            assert paths is not None
            summary = json.loads(Path(paths["summary"]).read_text("utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["failure_type"], "verification")
            self.assertEqual(summary["assertions"][0]["name"], "vc_meeting_active")
            self.assertFalse(summary["assertions"][0]["passed"])

    def test_final_verification_uses_runtime_hint_for_unknown_vc_meeting_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("发起视频会议并验证进入成功")
            recorder.record_action(
                1,
                "agent.done()",
                "done",
            )
            paths = recorder.finalize(
                "completed",
                final_observation=self._unknown_live_observation(),
            )

            self.assertIsNotNone(paths)
            assert paths is not None
            summary = json.loads(Path(paths["summary"]).read_text("utf-8"))
            self.assertEqual(summary["status"], "completed")
            self.assertTrue(summary["assertions"][0]["passed"])
            self.assertEqual(runtime["page_id"], "vc_meeting_active")
            self.assertEqual(runtime["final_state_source"], "runtime_semantic_hint")
            self.assertEqual(
                runtime["step_results"][-1]["locator_result"]["strategy"],
                "runtime_semantic_hint",
            )

    def test_final_verification_uses_runtime_hint_for_unknown_vc_invite_dialog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("在当前视频会议中打开邀请面板")
            recorder.record_action(
                1,
                "agent.done()",
                "done",
            )
            paths = recorder.finalize(
                "completed",
                final_observation=self._unknown_live_observation(),
            )

            self.assertIsNotNone(paths)
            assert paths is not None
            summary = json.loads(Path(paths["summary"]).read_text("utf-8"))
            self.assertEqual(summary["status"], "completed")
            self.assertTrue(summary["assertions"][0]["passed"])
            self.assertEqual(runtime["page_id"], "vc_invite_dialog")
            self.assertEqual(runtime["final_state_source"], "runtime_semantic_hint")

    def test_record_semantic_step_persists_replay_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("open chat")
            recorder.record_semantic_step(
                1,
                product="vc",
                page_type="vc_home",
                visible_controls=["start meeting", "join meeting"],
                action_summary="choose start meeting",
                verification="vc_start_preview_ready",
                verification_passed=True,
            )
            recorder.record_semantic_step(
                1,
                action_summary="choose visible start meeting entry",
            )
            paths = recorder.finalize("completed")

            self.assertIsNotNone(paths)
            assert paths is not None
            self.assertEqual(len(runtime["semantic_steps"]), 1)
            self.assertEqual(
                runtime["semantic_steps"][0]["action_summary"],
                "choose visible start meeting entry",
            )
            trace = json.loads(Path(paths["semantic_trace"]).read_text("utf-8"))
            replay = Path(paths["replay_draft"]).read_text("utf-8")
            self.assertEqual(trace[0]["page_type"], "vc_home")
            self.assertIn("choose visible start meeting entry", replay)
            self.assertNotIn("bbox", replay)
            self.assertNotIn("confidence", replay)
            self.assertNotIn("pyautogui", replay)

    def test_record_observation_records_semantic_anomaly_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = S3RuntimeRecorder(artifact_root=tmpdir)

            runtime = recorder.start("打开云文档并创建项目周报")
            recorder.record_observation(
                1,
                {"ocr_text": "飞书云文档 权限不足 申请权限"},
            )
            recorder.record_observation(
                1,
                {"ocr_text": "飞书云文档 权限不足 申请权限"},
            )
            paths = recorder.finalize("failed", failure_reason="permission blocker")

            self.assertIsNotNone(paths)
            self.assertEqual(len(runtime["anomaly_events"]), 1)
            event = runtime["anomaly_events"][0]
            self.assertEqual(event["step_index"], 1)
            self.assertEqual(event["product"], "docs")
            self.assertEqual(event["anomaly_type"], "permission_denied")
            self.assertEqual(event["recovery_hint"], "request_permission")
            serialized = json.dumps(runtime["anomaly_events"], ensure_ascii=False)
            self.assertNotIn("ocr_text", serialized)
            self.assertNotIn("bbox", serialized)
            self.assertNotIn("confidence", serialized)


if __name__ == "__main__":
    unittest.main()
