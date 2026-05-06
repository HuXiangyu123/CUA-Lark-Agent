"""Tests for the local Feishu evaluation dashboard server."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from gui_agents.feishu.reports.dashboard_server import (
    build_dashboard_payload,
    build_portal_html,
    discover_pending_runs,
    discover_report_runs,
    start_dashboard_server,
)


def _write_run(root: Path, run_id: str, *, status: str = "completed") -> None:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    screenshot_path = run_dir / "screenshots" / "step-001.png"
    summary = {
        "run_id": run_id,
        "task_id": "agentic_docs_create_doc",
        "product": "docs",
        "status": status,
        "result": "passed" if status == "completed" else "failed",
        "priority": "medium",
        "complexity": "medium",
        "steps": 3,
        "observed_steps": 3,
        "passed_steps": 3 if status == "completed" else 1,
        "failed_steps": 0 if status == "completed" else 2,
        "step_pass_rate": 1.0 if status == "completed" else 0.3333,
        "duration_sec": 2.5,
        "assertion_pass_rate": 1.0 if status == "completed" else 0.0,
        "step_efficiency": 1.0,
        "partial_credit": 1.0 if status == "completed" else 0.1667,
        "screenshot_count": 1,
        "reflection_count": 1,
        "redundant_action_rate": 0.0,
        "locator_stats": {
            "total": 1,
            "matched": 1 if status == "completed" else 0,
            "failed": 0 if status == "completed" else 1,
            "match_rate": 1.0 if status == "completed" else 0.0,
            "strategy_counts": {"agent_s3_runtime": 1},
        },
        "completion_signal": "done",
        "exec_error_count": 0,
        "exec_errors": [],
        "action_type_counts": {"click": 1, "done": 1},
        "failure_type": None if status == "completed" else "verification",
        "intent": "agent_s3_feishu",
        "assertions": [{"name": "docs_editor_ready", "passed": status == "completed"}],
        "step_artifacts": [
            {
                "step_id": "s3_step_001",
                "stage": "AGENT_S3_STEP",
                "action": "click",
                "status": "passed" if status == "completed" else "failed",
                "result": "passed" if status == "completed" else "failed",
                "assertion": "docs_editor_ready",
                "failure_reason": None if status == "completed" else "verification",
                "screenshot": str(screenshot_path),
            }
        ],
        "artifact_manifest": {
            "run_dir": str(run_dir),
            "summary": str(run_dir / "summary.json"),
            "report": str(run_dir / "report.md"),
            "actions": str(run_dir / "actions.jsonl"),
            "replay_draft": str(run_dir / "replay_draft.md"),
            "semantic_trace": str(run_dir / "semantic_trace.json"),
            "screenshots_count": 1,
            "final_screenshot": str(screenshot_path),
        },
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(
        "# Feishu Run Report\n\n## Summary\n- Status: `completed`\n",
        encoding="utf-8",
    )
    (run_dir / "replay_draft.md").write_text(
        "# Replay Draft\n\n## Step 1\n- Action: open docs editor\n",
        encoding="utf-8",
    )
    (run_dir / "semantic_trace.json").write_text(
        json.dumps(
            [{"step_id": "s3_step_001", "page_type": "docs_home"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    screenshots = run_dir / "screenshots"
    screenshots.mkdir()
    (screenshots / "step-001.png").write_bytes(b"fake")
    (run_dir / "actions.jsonl").write_text('{"action":"click"}\n', encoding="utf-8")


def _write_pending_run(root: Path, run_id: str) -> None:
    run_dir = root / run_id
    screenshots = run_dir / "screenshots"
    screenshots.mkdir(parents=True)
    (screenshots / "step-001.png").write_bytes(b"pending")
    (run_dir / "actions.jsonl").write_text('{"action":"click"}\n', encoding="utf-8")


class TestDashboardServer(unittest.TestCase):
    def test_discover_report_runs_reads_converted_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            _write_run(root, "run-a")

            runs = discover_report_runs(root)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "run-a")
        self.assertTrue(str(runs[0]["report_path"]).endswith("report.md"))
        self.assertTrue(str(runs[0]["replay_path"]).endswith("replay_draft.md"))
        self.assertEqual(runs[0]["screenshot_count"], 1)
        self.assertEqual(runs[0]["result"], "passed")

    def test_build_portal_html_lists_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            evaluation = Path(tmpdir) / "evaluation"
            _write_run(root, "run-a")

            html = build_portal_html(
                artifact_root=root, evaluation_dir=evaluation
            ).decode("utf-8")

        self.assertIn("飞书 Agent 评测控制台", html)
        self.assertIn("/runs/${encodeURIComponent(run.run_id)}/${kind}", html)
        self.assertIn("打开报告", html)
        self.assertIn("Run-a".lower(), html.lower())
        self.assertIn("Auto refresh", html)
        self.assertIn("pendingPanel", html)

    def test_discover_pending_runs_lists_partial_artifacts_without_summary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            _write_run(root, "run-a")
            _write_pending_run(root, "run-pending")

            pending = discover_pending_runs(root)
            payload = build_dashboard_payload(root)

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["run_id"], "run-pending")
        self.assertEqual(pending[0]["screenshot_count"], 1)
        self.assertIn("summary.json", pending[0]["missing_artifacts"])
        self.assertEqual(payload["pending_run_count"], 1)
        self.assertEqual(payload["pending_runs"][0]["run_id"], "run-pending")
        self.assertTrue(payload["dashboard_snapshot_id"])

    def test_dashboard_server_serves_dashboard_and_task_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            evaluation = Path(tmpdir) / "evaluation"
            _write_run(root, "run-a")
            _write_pending_run(root, "run-pending")
            handle = start_dashboard_server(
                artifact_root=root,
                evaluation_dir=evaluation,
                port=0,
            )
            try:
                root_url = handle.url.replace("/dashboard", "/")
                portal = urlopen(root_url, timeout=5).read().decode("utf-8")
                dashboard = urlopen(handle.url, timeout=5).read().decode("utf-8")
                api_payload = json.loads(
                    urlopen(
                        handle.url.replace("/dashboard", "/api/evaluation-summary"),
                        timeout=5,
                    )
                    .read()
                    .decode("utf-8")
                )
                report = (
                    urlopen(
                        handle.url.replace("/dashboard", "/runs/run-a/report"),
                        timeout=5,
                    )
                    .read()
                    .decode("utf-8")
                )
                replay = (
                    urlopen(
                        handle.url.replace("/dashboard", "/runs/run-a/replay"),
                        timeout=5,
                    )
                    .read()
                    .decode("utf-8")
                )
            finally:
                handle.stop()

        self.assertTrue(handle.url.endswith("/dashboard"))
        self.assertIn("飞书 Agent 评测控制台", portal)
        self.assertIn("飞书 Agent 评测控制台", dashboard)
        self.assertIn("打开报告", dashboard)
        self.assertIn("Auto refresh", dashboard)
        self.assertIn("Pending runs", dashboard)
        self.assertEqual(api_payload["pending_run_count"], 1)
        self.assertEqual(api_payload["pending_runs"][0]["run_id"], "run-pending")
        self.assertTrue(api_payload["dashboard_snapshot_id"])
        self.assertIn("Step Evidence", report)
        self.assertIn("过程质量 / Process Quality", report)
        self.assertIn("Action Distribution", report)
        self.assertIn("Locator Strategy", report)
        self.assertIn("Exec Errors", report)
        self.assertIn("运行报告 / run-a", report)
        self.assertIn("返回看板", report)
        self.assertIn("<svg", report)
        self.assertIn("quality-card", report)
        self.assertIn("<img", report)
        self.assertIn("--feishu: #1f7aff", report)
        self.assertIn('lang="zh-CN"', report)
        self.assertNotIn(">unknown<", report)
        self.assertNotIn("--acid", report)
        self.assertNotIn("Sitka Display", report)
        self.assertIn("Replay Draft", replay)

    def test_dashboard_server_serves_step_screenshot_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            evaluation = Path(tmpdir) / "evaluation"
            _write_run(root, "run-a")
            handle = start_dashboard_server(
                artifact_root=root,
                evaluation_dir=evaluation,
                port=0,
            )
            try:
                payload = urlopen(
                    handle.url.replace(
                        "/dashboard", "/runs/run-a/files/screenshots/step-001.png"
                    ),
                    timeout=5,
                ).read()
            finally:
                handle.stop()

        self.assertEqual(payload, b"fake")

    def test_dashboard_server_blocks_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            evaluation = Path(tmpdir) / "evaluation"
            _write_run(root, "run-a")
            handle = start_dashboard_server(
                artifact_root=root,
                evaluation_dir=evaluation,
                port=0,
            )
            try:
                with self.assertRaises(HTTPError) as raised:
                    urlopen(
                        handle.url.replace(
                            "/dashboard",
                            "/artifacts/evaluation/../test_runs/run-a/summary.json",
                        ),
                        timeout=5,
                    )
            finally:
                handle.stop()

        self.assertEqual(raised.exception.code, 404)

    def test_dashboard_server_handle_stop_joins_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            evaluation = Path(tmpdir) / "evaluation"
            _write_run(root, "run-a")
            handle = start_dashboard_server(
                artifact_root=root,
                evaluation_dir=evaluation,
                port=0,
            )
            thread = handle.thread
            self.assertIsInstance(thread, threading.Thread)
            self.assertTrue(thread.is_alive())
            handle.stop()

        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
