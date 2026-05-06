import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher


class LauncherEnvRoutingTest(unittest.TestCase):
    def _fresh_config(self) -> dict:
        return copy.deepcopy(launcher.DEFAULT_CONFIG)

    def test_default_execution_mode_is_feishu_agent(self) -> None:
        self.assertEqual(launcher.DEFAULT_CONFIG["execution_mode"], "feishu_agent")

    def test_load_config_defaults_execution_mode_to_feishu_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = str(Path(tmpdir) / "missing-config.json")
            with (
                patch.object(launcher, "CONFIG_FILE", config_path),
                patch.object(launcher, "_parse_env_txt", return_value={}),
            ):
                cfg = launcher.load_config()

        self.assertEqual(cfg["execution_mode"], "feishu_agent")

    def test_load_config_repairs_invalid_execution_mode_to_feishu_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps({"execution_mode": "legacy_worker"}),
                encoding="utf-8",
            )
            with (
                patch.object(launcher, "CONFIG_FILE", str(config_path)),
                patch.object(launcher, "_parse_env_txt", return_value={}),
            ):
                cfg = launcher.load_config()

        self.assertEqual(cfg["execution_mode"], "feishu_agent")

    def test_env_defaults_split_main_and_ground_ark_keys(self) -> None:
        cfg = self._fresh_config()
        env = {
            "ep-id": "ep-main-123",
            "api-key": "ark-main-key",
            "ARK_API_KEY": "ark-ground-key",
        }

        with patch.object(launcher, "_parse_env_txt", return_value=env):
            launcher._apply_env_defaults(cfg, had_main_routing=False)

        self.assertEqual(cfg["main_providers"]["volcano"]["model_id"], "ep-main-123")
        self.assertEqual(
            cfg["main_providers"]["volcano"]["model_api_key"], "ark-main-key"
        )
        self.assertEqual(
            cfg["ground_providers"]["doubao_ark"]["api_key"], "ark-ground-key"
        )

    def test_env_defaults_fallback_to_ground_key_when_main_key_missing(self) -> None:
        cfg = self._fresh_config()
        env = {
            "ep-id": "ep-main-123",
            "ARK_API_KEY": "ark-shared-key",
        }

        with patch.object(launcher, "_parse_env_txt", return_value=env):
            launcher._apply_env_defaults(cfg, had_main_routing=False)

        self.assertEqual(
            cfg["main_providers"]["volcano"]["model_api_key"], "ark-shared-key"
        )
        self.assertEqual(
            cfg["ground_providers"]["doubao_ark"]["api_key"], "ark-shared-key"
        )

    def test_env_defaults_repairs_legacy_main_key_fallback(self) -> None:
        cfg = self._fresh_config()
        cfg["main_providers"]["volcano"]["model_api_key"] = "ark-ground-key"
        env = {
            "ep-id": "ep-main-123",
            "api-key": "ark-main-key",
            "ARK_API_KEY": "ark-ground-key",
        }

        with patch.object(launcher, "_parse_env_txt", return_value=env):
            launcher._apply_env_defaults(cfg, had_main_routing=True)

        self.assertEqual(
            cfg["main_providers"]["volcano"]["model_api_key"], "ark-main-key"
        )

    def test_openai_env_does_not_override_default_doubao_main_provider(self) -> None:
        cfg = self._fresh_config()
        env = {
            "ep-id": "ep-main-123",
            "api-key": "ark-main-key",
            "oai_api": "openai-key",
            "oai_model": "gpt-5.4",
            "oai_base_url": "https://example.test/v1",
        }

        with patch.object(launcher, "_parse_env_txt", return_value=env):
            launcher._apply_env_defaults(cfg, had_main_routing=False)

        self.assertEqual(cfg["main_provider"], "volcano")
        self.assertEqual(cfg["model_id"], "ep-main-123")
        self.assertEqual(
            cfg["main_providers"]["openai_gpt"]["model_api_key"], "openai-key"
        )

    def test_load_config_defaults_to_doubao_when_only_openai_env_exists(self) -> None:
        env = {
            "oai_api": "openai-key",
            "oai_model": "gpt-5.4",
            "oai_base_url": "https://example.test/v1",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = str(Path(tmpdir) / "missing-config.json")
            with (
                patch.object(launcher, "CONFIG_FILE", config_path),
                patch.object(launcher, "_parse_env_txt", return_value=env),
            ):
                cfg = launcher.load_config()

        self.assertEqual(cfg["main_provider"], "volcano")
        self.assertEqual(cfg["main_providers"]["openai_gpt"]["model_id"], "gpt-5.4")

    def test_explicit_openai_main_provider_is_preserved(self) -> None:
        raw = {
            "main_provider": "openai_gpt",
            "main_providers": {
                "openai_gpt": {
                    "model_api_key": "saved-openai-key",
                    "model_id": "gpt-5.4",
                    "model_url": "https://example.test/v1",
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with (
                patch.object(launcher, "CONFIG_FILE", str(config_path)),
                patch.object(launcher, "_parse_env_txt", return_value={}),
            ):
                cfg = launcher.load_config()

        self.assertEqual(cfg["main_provider"], "openai_gpt")
        self.assertEqual(cfg["model_id"], "gpt-5.4")

    def test_discovers_semantic_replay_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run_001"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "run_001",
                        "product": "vc",
                        "status": "completed",
                        "task_title": "start meeting",
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "semantic_trace.json").write_text("[]\n", encoding="utf-8")
            (run_dir / "replay_draft.md").write_text(
                "# Replay Draft\n", encoding="utf-8"
            )
            screenshots_dir = run_dir / "screenshots"
            screenshots_dir.mkdir()
            (screenshots_dir / "step.png").write_bytes(b"png")
            ignored = root / "empty_run"
            ignored.mkdir()

            runs = launcher.discover_semantic_replay_runs(root)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "run_001")
        self.assertEqual(runs[0]["product"], "vc")
        self.assertEqual(runs[0]["screenshots_count"], 1)
        self.assertTrue(runs[0]["replay_draft"].endswith("replay_draft.md"))

    def test_discovers_legacy_replay_run_without_semantic_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "legacy_run"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy_run",
                        "product": "im",
                        "status": "failed",
                        "task_title": "legacy report",
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "report.md").write_text("# Legacy Report\n", encoding="utf-8")
            (run_dir / "actions.jsonl").write_text("{}\n", encoding="utf-8")
            screenshots_dir = run_dir / "screenshots"
            screenshots_dir.mkdir()
            (screenshots_dir / "step.png").write_bytes(b"png")

            runs = launcher.discover_semantic_replay_runs(root)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "legacy_run")
        self.assertIsNone(runs[0]["semantic_trace"])
        self.assertIsNone(runs[0]["replay_draft"])
        self.assertTrue(runs[0]["report"].endswith("report.md"))
        self.assertTrue(runs[0]["run_dir"].endswith("legacy_run"))
        self.assertEqual(runs[0]["screenshots_count"], 1)

    def test_load_replay_draft_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            replay_path = Path(tmpdir) / "replay_draft.md"
            replay_path.write_text("# Replay Draft\nStep content\n", encoding="utf-8")

            preview = launcher.load_replay_draft_preview(replay_path, limit=10)

        self.assertIn("# Replay", preview)
        self.assertIn("preview truncated", preview)

    def test_load_replay_artifact_preview_falls_back_to_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.md"
            report_path.write_text("# Legacy Report\nStep content\n", encoding="utf-8")
            run = {"replay_draft": None, "report": str(report_path)}

            preview = launcher.load_replay_artifact_preview(run)

        self.assertIn("旧版 report.md", preview)
        self.assertIn("# Legacy Report", preview)

    def test_load_semantic_trace_steps_filters_quantitative_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "semantic_trace.json"
            trace_path.write_text(
                json.dumps(
                    [
                        {
                            "step_index": 1,
                            "step_id": "s3_step_001",
                            "product": "vc",
                            "page_type": "vc_home",
                            "visible_controls": [
                                "start_card",
                                "bbox leaked control",
                            ],
                            "action_summary": "click visible control",
                            "verification": "vc_home_ready",
                            "verification_passed": True,
                            "bbox": [1, 2, 3, 4],
                            "confidence": 0.99,
                            "action_code": "pyautogui.click(10, 20)",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            steps = launcher.load_semantic_trace_steps(trace_path)

        serialized = json.dumps(steps, ensure_ascii=False)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["visible_controls"], ["start_card"])
        self.assertNotIn("bbox", serialized)
        self.assertNotIn("confidence", serialized)
        self.assertNotIn("pyautogui", serialized)

    def test_replay_step_label_and_detail_are_human_readable(self) -> None:
        step = {
            "step_id": "s3_step_001",
            "product": "vc",
            "page_type": "vc_home",
            "visible_controls": ["start_card", "join_card"],
            "action_summary": "click visible control",
            "verification": "runtime_step",
            "verification_passed": False,
            "failure_type": "runtime",
        }

        label = launcher.format_replay_step_label(step, 1)
        detail = launcher.render_replay_step_detail(step, 1)

        self.assertIn("01 | failed | vc_home", label)
        self.assertIn("Visible controls: start_card, join_card", detail)
        self.assertIn("Verification: runtime_step (failed)", detail)
        self.assertIn("Failure type: runtime", detail)

    def test_replay_review_summary_flags_gaps(self) -> None:
        run = {
            "run_id": "run_001",
            "product": "vc",
            "status": "failed",
            "semantic_trace": "semantic_trace.json",
            "replay_draft": "replay_draft.md",
            "screenshots_count": 0,
        }
        steps = [
            {
                "step_id": "s3_step_001",
                "product": "vc",
                "page_type": "vc_home",
                "action_summary": "click visible control",
                "verification": "runtime_step",
                "verification_passed": True,
            },
            {
                "step_id": "s3_step_002",
                "product": "vc",
                "page_type": "vc_start_preview",
                "verification_passed": False,
                "failure_type": "runtime",
                "recovery_attempt": True,
            },
        ]

        summary = launcher.build_replay_review_summary(run, steps)
        rendered = launcher.render_replay_review_summary(run, steps)

        self.assertEqual(summary["steps"], 2)
        self.assertEqual(summary["passed_steps"], 1)
        self.assertEqual(summary["failed_steps"], 1)
        self.assertEqual(summary["recovery_steps"], 1)
        self.assertIn("no screenshots", summary["warnings"])
        self.assertIn("step 2 missing action", rendered)
        self.assertIn("vc_home -> vc_start_preview", rendered)

    def test_mark_run_aborted_writes_summary_and_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run_abort"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                json.dumps({"run_id": "run_abort", "status": "running"}),
                encoding="utf-8",
            )
            (run_dir / "replay_draft.md").write_text(
                "# Replay Draft\n",
                encoding="utf-8",
            )

            summary = launcher.mark_run_aborted(
                run_dir,
                reason="test manual stop",
            )

            persisted = json.loads((run_dir / "summary.json").read_text("utf-8"))
            replay = (run_dir / "replay_draft.md").read_text(encoding="utf-8")
            report = (run_dir / "report.md").read_text(encoding="utf-8")

        self.assertEqual(summary["status"], "aborted")
        self.assertEqual(summary["result"], "aborted")
        self.assertEqual(persisted["failure_type"], "manual_stop")
        self.assertIn("test manual stop", replay)
        self.assertIn("Manual Stop", report)


if __name__ == "__main__":
    unittest.main()
