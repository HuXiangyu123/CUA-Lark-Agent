import json
import tempfile
import unittest
from pathlib import Path

from gui_agents.feishu.maintenance.artifact_manager import ArtifactManager
from gui_agents.feishu.reports.report_builder import ReportBuilder


class TestReportBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.testcase = {
            "id": "tc_im_send_message_001",
            "product": "im",
            "title": "send message",
            "priority": "high",
            "complexity": "medium",
            "steps": [{}, {}, {}],
            "assertions": ["chat_title_matched", "message_sent"],
        }
        self.runtime = {
            "run_id": "20260506_010203",
            "status": "failed",
            "intent": "send_message",
            "params": {"chat_name": "bot功能测试", "message_text": "hello"},
            "page_id": "chat_main",
            "precondition_results": [],
            "action_logs": [
                {
                    "timestamp": "2026-05-06T01:02:04+08:00",
                    "step_id": "step_3",
                    "stage": "SEND_MESSAGE",
                    "action": "send_message",
                    "target": "send_button",
                    "params": {"text": "hello"},
                    "status": "failed",
                }
            ],
            "reflections": ["previous action did not complete the expected send state"],
            "screenshots": ["artifacts/test_runs/20260506_010203/screenshots/step.png"],
            "step_results": [
                {
                    "step_id": "step_1",
                    "stage": "ENSURE_CHAT_OPEN",
                    "action": "open_chat",
                    "target": "bot功能测试",
                    "status": "passed",
                    "locator_result": {
                        "matched": True,
                        "strategy": "state_detector",
                    },
                    "verification_result": {
                        "assertion": "chat_title_matched",
                        "passed": True,
                        "failure_reason": None,
                    },
                    "failure_type": None,
                    "failure_reason": None,
                },
                {
                    "step_id": "step_3",
                    "stage": "SEND_MESSAGE",
                    "action": "send_message",
                    "target": "send_button",
                    "status": "failed",
                    "locator_result": {
                        "matched": False,
                        "strategy": "agent_s3_runtime",
                    },
                    "verification_result": {
                        "assertion": "message_sent",
                        "passed": False,
                        "failure_reason": "sent message mismatch",
                    },
                    "failure_type": "verification",
                    "failure_reason": "sent message mismatch",
                },
            ],
            "failure_type": "verification",
            "failure_reason": "sent message mismatch",
            "anomaly_events": [
                {
                    "step_index": 2,
                    "timestamp": "2026-05-06T01:02:04+08:00",
                    "product": "im",
                    "page_type": "chat_main",
                    "anomaly_type": "blocking_modal",
                    "recovery_hint": "close_modal_or_wait",
                    "ocr_text": "should not be reported",
                    "bbox": [1, 2, 3, 4],
                    "confidence": 0.99,
                }
            ],
            "started_at": "2026-05-06T01:02:03+08:00",
        }

    def test_build_summary_counts_steps_and_assertions(self) -> None:
        builder = ReportBuilder()
        summary = builder.build_summary(self.testcase, self.runtime)

        self.assertEqual(summary["task_id"], "tc_im_send_message_001")
        self.assertEqual(summary["priority"], "high")
        self.assertEqual(summary["complexity"], "medium")
        self.assertEqual(summary["intent"], "send_message")
        self.assertEqual(summary["steps"], 3)
        self.assertEqual(summary["planned_steps"], 3)
        self.assertEqual(summary["observed_steps"], 2)
        self.assertEqual(summary["passed_steps"], 1)
        self.assertEqual(summary["failed_steps"], 1)
        self.assertEqual(summary["result"], "failed")
        self.assertEqual(summary["failure_type"], "verification")
        self.assertEqual(summary["screenshot_count"], 1)
        self.assertEqual(summary["action_type_counts"]["send_message"], 1)
        self.assertEqual(summary["completion_signal"], "send_message")
        self.assertEqual(summary["partial_credit"], 0.5)
        self.assertEqual(summary["reflection_count"], 1)
        self.assertEqual(summary["redundant_action_rate"], 0.0)
        self.assertEqual(summary["locator_stats"]["total"], 2)
        self.assertEqual(summary["locator_stats"]["matched"], 1)
        self.assertEqual(summary["locator_stats"]["match_rate"], 0.5)
        self.assertEqual(summary["exec_error_count"], 1)
        self.assertEqual(summary["anomaly_events_count"], 1)
        self.assertEqual(summary["anomaly_type_counts"]["blocking_modal"], 1)
        self.assertEqual(summary["anomaly_events"][0]["step_index"], 2)
        self.assertEqual(summary["anomaly_events"][0]["anomaly_type"], "blocking_modal")
        self.assertNotIn("ocr_text", summary["anomaly_events"][0])
        self.assertNotIn("bbox", summary["anomaly_events"][0])
        self.assertNotIn("confidence", summary["anomaly_events"][0])
        self.assertEqual(summary["assertion_passed"], 1)
        self.assertEqual(summary["assertion_failed"], 1)
        self.assertEqual(summary["assertions"][0]["name"], "chat_title_matched")
        self.assertTrue(summary["assertions"][0]["passed"])
        self.assertEqual(summary["assertions"][1]["name"], "message_sent")
        self.assertFalse(summary["assertions"][1]["passed"])
        self.assertEqual(
            summary["step_artifacts"][0]["screenshot"], self.runtime["screenshots"][0]
        )

    def test_build_markdown_includes_summary_and_steps(self) -> None:
        builder = ReportBuilder()
        summary = builder.build_summary(self.testcase, self.runtime)
        markdown = builder.build_markdown(summary, self.runtime, testcase=self.testcase)

        self.assertIn("# Feishu Run Report", markdown)
        self.assertIn("## Execution Trace", markdown)
        self.assertIn("## Step Gallery", markdown)
        self.assertIn("Partial Credit", markdown)
        self.assertIn("Locator Stats", markdown)
        self.assertIn("`send_message`", markdown)
        self.assertIn("`step_3`", markdown)
        self.assertIn("sent message mismatch", markdown)
        self.assertIn("step.png", markdown)
        self.assertIn("## Anomaly Events", markdown)
        self.assertIn("blocking_modal", markdown)
        self.assertIn("close_modal_or_wait", markdown)
        self.assertNotIn("should not be reported", markdown)
        self.assertNotIn("bbox", markdown)
        self.assertNotIn("confidence", markdown)

    def test_write_runtime_artifacts_persists_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = ReportBuilder(ArtifactManager(tmpdir))
            paths = builder.write_runtime_artifacts(self.testcase, self.runtime)
            summary = Path(paths["summary"]).read_text(encoding="utf-8")

            self.assertTrue(Path(paths["summary"]).exists())
            self.assertTrue(Path(paths["report"]).exists())
            self.assertTrue(Path(paths["actions"]).exists())
            self.assertIn("artifact_manifest", summary)
            self.assertIn("screenshots_count", summary)

    def test_build_semantic_trace_strips_quantitative_fields(self) -> None:
        runtime = {
            "run_id": "semantic_run",
            "anomaly_events": [
                {
                    "step_index": 1,
                    "product": "vc",
                    "page_type": "vc_home",
                    "anomaly_type": "loading",
                    "recovery_hint": "retry_after_load",
                    "ocr_text": "加载中",
                    "bbox": [1, 2, 3, 4],
                    "confidence": 0.99,
                }
            ],
            "semantic_steps": [
                {
                    "step_index": 1,
                    "step_id": "s3_step_001",
                    "product": "vc",
                    "page_type": "vc_home",
                    "visible_controls": [
                        "start meeting",
                        "bbox leaked control",
                        "join meeting",
                    ],
                    "action_summary": "choose start meeting",
                    "verification": "vc_start_preview_ready",
                    "verification_passed": True,
                    "failure_type": None,
                    "recovery_attempt": False,
                    "timestamp": "2026-05-06T01:02:04+08:00",
                    "bbox": [1, 2, 3, 4],
                    "confidence": 0.99,
                    "action_code": "pyautogui.click(10, 20)",
                    "x": 10,
                    "y": 20,
                }
            ],
        }

        trace = ReportBuilder().build_semantic_trace(runtime)
        serialized = str(trace)

        self.assertEqual(trace[0]["action_summary"], "choose start meeting")
        self.assertEqual(trace[0]["anomalies"], ["loading"])
        self.assertEqual(trace[0]["recovery_hint"], "retry_after_load")
        self.assertEqual(
            trace[0]["visible_controls"], ["start meeting", "join meeting"]
        )
        self.assertNotIn("bbox", serialized)
        self.assertNotIn("confidence", serialized)
        self.assertNotIn("ocr_text", serialized)
        self.assertNotIn("pyautogui.click", serialized)
        self.assertNotIn("'x'", serialized)
        self.assertNotIn("'y'", serialized)

    def test_build_replay_draft_is_human_review_artifact(self) -> None:
        runtime = {
            "run_id": "semantic_run",
            "task_title": "start meeting",
            "semantic_steps": [
                {
                    "step_index": 1,
                    "step_id": "s3_step_001",
                    "product": "vc",
                    "page_type": "vc_home",
                    "visible_controls": ["start meeting", "join meeting"],
                    "action_summary": "choose start meeting",
                    "verification": "vc_start_preview_ready",
                    "verification_passed": True,
                    "timestamp": "2026-05-06T01:02:04+08:00",
                }
            ],
        }

        markdown = ReportBuilder().build_replay_draft(runtime)

        self.assertIn("# Replay Draft - Run semantic_run", markdown)
        self.assertIn("- Page: vc:vc_home", markdown)
        self.assertIn("- Action: choose start meeting", markdown)
        self.assertIn("- Verify: vc_start_preview_ready (passed)", markdown)
        self.assertIn("not executable", markdown)
        self.assertNotIn("bbox", markdown)
        self.assertNotIn("confidence", markdown)
        self.assertNotIn("coordinate", markdown.lower())

    def test_build_replay_draft_includes_anomaly_only_trace_entry(self) -> None:
        runtime = {
            "run_id": "anomaly_run",
            "task_title": "open docs",
            "anomaly_events": [
                {
                    "step_index": 1,
                    "product": "docs",
                    "page_type": "docs_browser_editor",
                    "anomaly_type": "permission_denied",
                    "recovery_hint": "request_permission",
                    "ocr_text": "权限不足",
                    "confidence": 0.99,
                }
            ],
            "semantic_steps": [],
        }

        trace = ReportBuilder().build_semantic_trace(runtime)
        markdown = ReportBuilder().build_replay_draft(runtime)

        self.assertEqual(trace[0]["step_id"], "anomaly_step_001")
        self.assertEqual(trace[0]["anomalies"], ["permission_denied"])
        self.assertIn("- Anomalies: permission_denied", markdown)
        self.assertIn("- Recovery hint: request_permission", markdown)
        self.assertIn("not executable", markdown)
        self.assertNotIn("ocr_text", markdown)
        self.assertNotIn("confidence", markdown)

    def test_write_runtime_artifacts_persists_semantic_trace_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = dict(self.runtime)
            runtime["semantic_steps"] = [
                {
                    "step_index": 1,
                    "step_id": "s3_step_001",
                    "product": "im",
                    "page_type": "chat_main",
                    "action_summary": "send message",
                    "verification": "message_sent",
                    "verification_passed": True,
                    "timestamp": "2026-05-06T01:02:04+08:00",
                }
            ]
            builder = ReportBuilder(ArtifactManager(tmpdir))
            paths = builder.write_runtime_artifacts(self.testcase, runtime)

            self.assertTrue(Path(paths["semantic_trace"]).exists())
            self.assertTrue(Path(paths["replay_draft"]).exists())

    def test_build_summary_supports_docs_agentic_runtime(self) -> None:
        testcase = {
            "id": "tc_docs_create_doc_001",
            "product": "docs",
            "title": "create doc",
            "steps": [{}, {}, {}, {}, {}],
            "assertions": ["doc_editor_ready", "doc_title_contains_text"],
        }
        runtime = {
            "run_id": "20260506_docs",
            "status": "passed",
            "intent": "create_doc_and_edit",
            "params": {"doc_title": "项目周报", "body_text": None},
            "page_id": "docs_browser_editor",
            "precondition_results": [],
            "action_logs": [],
            "screenshots": [],
            "step_results": [
                {
                    "step_id": "docs_wf_step_4",
                    "stage": "SELECT_BLANK_DOC",
                    "action": "select_blank_doc_template",
                    "target": "docs_blank_doc_card",
                    "status": "passed",
                    "locator_result": {},
                    "verification_result": {
                        "assertion": "doc_editor_ready",
                        "passed": True,
                        "failure_reason": None,
                    },
                    "failure_type": None,
                    "failure_reason": None,
                },
                {
                    "step_id": "docs_wf_step_5",
                    "stage": "TYPE_DOC_TITLE",
                    "action": "type_doc_title",
                    "target": "docs_title_input",
                    "status": "passed",
                    "locator_result": {},
                    "verification_result": {
                        "assertion": "doc_title_contains_text",
                        "passed": True,
                        "failure_reason": None,
                    },
                    "failure_type": None,
                    "failure_reason": None,
                },
            ],
            "failure_type": None,
            "failure_reason": None,
            "started_at": "2026-05-06T01:02:03+08:00",
        }

        summary = ReportBuilder().build_summary(testcase, runtime)

        self.assertEqual(summary["product"], "docs")
        self.assertEqual(summary["intent"], "create_doc_and_edit")
        self.assertEqual(summary["failed_steps"], 0)
        self.assertTrue(summary["assertions"][0]["passed"])

    def test_build_summary_supports_base_agentic_runtime(self) -> None:
        testcase = {
            "id": "tc_base_agentic_runtime_001",
            "product": "base",
            "title": "base semantic runtime",
            "steps": [{}, {}],
            "assertions": ["base_home_ready", "base_editor_ready"],
        }
        runtime = {
            "run_id": "20260506_base",
            "status": "passed",
            "intent": "base_semantic_task",
            "params": {},
            "page_id": "base_browser_table",
            "precondition_results": [],
            "action_logs": [],
            "screenshots": [],
            "step_results": [
                {
                    "step_id": "base_agent_step_1",
                    "stage": "OBSERVE_BASE_HOME",
                    "action": "click",
                    "target": "base home new button",
                    "status": "passed",
                    "locator_result": {},
                    "verification_result": {
                        "assertion": "base_home_ready",
                        "passed": True,
                        "failure_reason": None,
                    },
                    "failure_type": None,
                    "failure_reason": None,
                },
                {
                    "step_id": "base_agent_step_2",
                    "stage": "OBSERVE_BASE_EDITOR",
                    "action": "click",
                    "target": "blank base table card",
                    "status": "passed",
                    "locator_result": {},
                    "verification_result": {
                        "assertion": "base_editor_ready",
                        "passed": True,
                        "failure_reason": None,
                    },
                    "failure_type": None,
                    "failure_reason": None,
                },
            ],
            "failure_type": None,
            "failure_reason": None,
            "started_at": "2026-05-06T01:02:03+08:00",
        }

        summary = ReportBuilder().build_summary(testcase, runtime)

        self.assertEqual(summary["product"], "base")
        self.assertEqual(summary["intent"], "base_semantic_task")
        self.assertEqual(summary["failed_steps"], 0)
        self.assertTrue(summary["assertions"][1]["passed"])

    def test_build_summary_uses_runtime_identity_without_testcase(self) -> None:
        runtime = {
            "run_id": "20260506_vc",
            "status": "completed",
            "intent": "agent_s3_feishu",
            "params": {"instruction": "发起视频会议并验证进入成功"},
            "product": "vc",
            "task_id": "agentic_vc_start_meeting",
            "task_title": "发起视频会议并验证进入成功",
            "assertion_plan": [{"assertion": "vc_meeting_active", "expected": {}}],
            "page_id": "vc_meeting_active",
            "precondition_results": [],
            "action_logs": [],
            "screenshots": [],
            "step_results": [
                {
                    "step_id": "final_assertion_1",
                    "stage": "FINAL_ASSERTION",
                    "action": "verify_assertion",
                    "target": "vc_meeting_active",
                    "status": "passed",
                    "locator_result": {},
                    "verification_result": {
                        "assertion": "vc_meeting_active",
                        "passed": True,
                        "failure_reason": None,
                    },
                    "failure_type": None,
                    "failure_reason": None,
                }
            ],
            "failure_type": None,
            "failure_reason": None,
            "started_at": "2026-05-06T01:02:03+08:00",
        }

        summary = ReportBuilder().build_summary(None, runtime)

        self.assertEqual(summary["product"], "vc")
        self.assertEqual(summary["task_id"], "agentic_vc_start_meeting")
        self.assertEqual(summary["result"], "passed")
        self.assertEqual(summary["assertions"][0]["name"], "vc_meeting_active")
        self.assertTrue(summary["assertions"][0]["passed"])

    def test_build_summary_uses_stable_defaults_without_unknown_labels(self) -> None:
        runtime = {
            "run_id": "defaults_run",
            "status": "completed",
            "intent": "agent_s3_feishu",
            "params": {},
            "task_id": None,
            "assertion_plan": [],
            "action_logs": [],
            "screenshots": [],
            "step_results": [],
            "started_at": "2026-05-06T01:02:03+08:00",
        }

        summary = ReportBuilder().build_summary(None, runtime)
        serialized = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["product"], "general")
        self.assertEqual(summary["task_id"], "ad_hoc_task")
        self.assertEqual(summary["priority"], "medium")
        self.assertEqual(summary["complexity"], "low")
        self.assertEqual(summary["completion_signal"], "status_completed")
        self.assertEqual(summary["reflection_count"], 0)
        self.assertEqual(summary["redundant_action_rate"], 0.0)
        self.assertNotIn('"unknown"', serialized)
