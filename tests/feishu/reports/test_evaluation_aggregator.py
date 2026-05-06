"""Tests for offline Feishu batch evaluation aggregation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gui_agents.feishu.reports.evaluation_aggregator import (
    build_evaluation_dashboard_html,
    build_evaluation_markdown,
    build_evaluation_summary,
    build_live_e2e_evidence,
    build_live_e2e_markdown,
    discover_run_summaries,
    write_evaluation_report,
)


def _write_summary(root: Path, run_id: str, payload: dict[str, object]) -> None:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    data = {
        "run_id": run_id,
        "task_id": "agentic_im_send_message",
        "product": "im",
        "priority": "high",
        "complexity": "medium",
        "status": "completed",
        "result": "passed",
        "steps": 2,
        "observed_steps": 2,
        "passed_steps": 2,
        "failed_steps": 0,
        "step_pass_rate": 1.0,
        "duration_sec": 1.25,
        "assertion_pass_rate": 1.0,
        "step_efficiency": 1.0,
        "partial_credit": 1.0,
        "screenshot_count": 1,
        "action_type_counts": {"click": 1, "done": 1},
        "completion_signal": "done",
        "reflection_count": 0,
        "redundant_action_rate": 0.0,
        "locator_stats": {
            "total": 1,
            "matched": 1,
            "failed": 0,
            "match_rate": 1.0,
            "strategy_counts": {"agent_s3_runtime": 1},
        },
        "exec_error_count": 0,
        "exec_errors": [],
        "failure_type": None,
        "failure_reason": None,
        "artifact_manifest": {
            "run_dir": str(run_dir),
            "summary": str(run_dir / "summary.json"),
            "report": str(run_dir / "report.md"),
            "actions": str(run_dir / "actions.jsonl"),
            "screenshots_count": 1,
            "final_screenshot": str(
                run_dir / "screenshots" / "s3_step_001_observation.png"
            ),
        },
    }
    data.update(payload)
    (run_dir / "summary.json").write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_live_artifacts(run_dir: Path) -> None:
    (run_dir / "report.md").write_text("# report\n", encoding="utf-8")
    (run_dir / "actions.jsonl").write_text('{"action":"done"}\n', encoding="utf-8")
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    (screenshots_dir / "s3_step_001_observation.png").write_bytes(b"png")


class TestEvaluationAggregator(unittest.TestCase):
    def test_discovers_run_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_summary(root, "run-a", {})
            _write_summary(root, "run-b", {"status": "failed"})
            (root / "not-a-run").mkdir()

            summaries = discover_run_summaries(root)

        self.assertEqual([item["run_id"] for item in summaries], ["run-a", "run-b"])
        self.assertTrue(all("_summary_path" in item for item in summaries))

    def test_builds_success_and_failure_aggregates(self) -> None:
        summaries = [
            {
                "run_id": "run-a",
                "task_id": "agentic_im_send_message",
                "product": "im",
                "priority": "high",
                "complexity": "medium",
                "status": "completed",
                "result": "passed",
                "steps": 2,
                "observed_steps": 2,
                "passed_steps": 2,
                "failed_steps": 0,
                "step_pass_rate": 1.0,
                "duration_sec": 1.0,
                "assertion_pass_rate": 1.0,
                "step_efficiency": 1.0,
                "partial_credit": 1.0,
                "screenshot_count": 2,
                "action_type_counts": {"click": 1, "done": 1},
                "completion_signal": "done",
                "reflection_count": 0,
                "redundant_action_rate": 0.0,
                "locator_stats": {
                    "total": 2,
                    "matched": 2,
                    "failed": 0,
                    "match_rate": 1.0,
                    "strategy_counts": {"agent_s3_runtime": 2},
                },
                "exec_error_count": 0,
                "exec_errors": [],
                "failure_type": None,
                "artifact_manifest": {
                    "summary": "summary-a",
                    "report": "report-a",
                    "actions": "actions-a",
                    "screenshots_count": 2,
                },
            },
            {
                "run_id": "run-b",
                "task_id": "agentic_docs_create_doc",
                "product": "docs",
                "priority": "medium",
                "complexity": "high",
                "status": "failed",
                "result": "failed",
                "steps": 3,
                "observed_steps": 3,
                "passed_steps": 1,
                "failed_steps": 2,
                "step_pass_rate": 0.3333,
                "duration_sec": 5.0,
                "assertion_pass_rate": 0.5,
                "step_efficiency": 0.6667,
                "partial_credit": 0.4167,
                "screenshot_count": 1,
                "action_type_counts": {"click": 2, "fail": 1},
                "completion_signal": "fail",
                "reflection_count": 2,
                "redundant_action_rate": 0.3333,
                "locator_stats": {
                    "total": 3,
                    "matched": 1,
                    "failed": 2,
                    "match_rate": 0.3333,
                    "strategy_counts": {"agent_s3_runtime": 2, "state_detector": 1},
                },
                "exec_error_count": 1,
                "exec_errors": [
                    {
                        "step_id": "step-3",
                        "action": "click",
                        "status": "failed",
                        "failure_reason": "exec failed",
                    }
                ],
                "failure_type": "verification",
                "artifact_manifest": {
                    "summary": "summary-b",
                    "report": "report-b",
                    "actions": "actions-b",
                    "screenshots_count": 1,
                },
            },
        ]

        evaluation = build_evaluation_summary(
            summaries,
            generated_at="2026-05-06T00:00:00+08:00",
        )

        self.assertEqual(evaluation["total_runs"], 2)
        self.assertEqual(evaluation["completed_runs"], 1)
        self.assertEqual(evaluation["failed_runs"], 1)
        self.assertEqual(evaluation["success_rate"], 0.5)
        self.assertEqual(evaluation["average_duration_sec"], 3.0)
        self.assertEqual(evaluation["average_steps"], 2.5)
        self.assertEqual(evaluation["average_observed_steps"], 2.5)
        self.assertEqual(evaluation["passed_steps"], 3)
        self.assertEqual(evaluation["failed_steps"], 2)
        self.assertEqual(evaluation["average_step_pass_rate"], 0.6666)
        self.assertEqual(evaluation["average_assertion_pass_rate"], 0.75)
        self.assertEqual(evaluation["average_screenshot_count"], 1.5)
        self.assertEqual(evaluation["average_step_efficiency"], 0.8334)
        self.assertEqual(evaluation["average_partial_credit"], 0.7084)
        self.assertEqual(evaluation["average_reflection_count"], 1.0)
        self.assertEqual(evaluation["average_redundant_action_rate"], 0.1666)
        self.assertEqual(evaluation["average_locator_match_rate"], 0.6666)
        self.assertEqual(evaluation["total_exec_errors"], 1)
        self.assertEqual(evaluation["exec_error_runs"], 1)
        self.assertEqual(evaluation["artifact_complete_runs"], 2)
        self.assertEqual(
            evaluation["action_type_totals"], {"click": 3, "done": 1, "fail": 1}
        )
        self.assertEqual(evaluation["completion_signal_counts"], {"done": 1, "fail": 1})
        self.assertEqual(
            evaluation["locator_strategy_totals"],
            {"agent_s3_runtime": 4, "state_detector": 1},
        )
        self.assertEqual(evaluation["by_product"]["im"]["success_rate"], 1.0)
        self.assertEqual(evaluation["by_product"]["docs"]["success_rate"], 0.0)
        self.assertEqual(evaluation["by_priority"]["high"]["success_rate"], 1.0)
        self.assertEqual(evaluation["by_complexity"]["high"]["success_rate"], 0.0)
        self.assertEqual(evaluation["by_failure_type"], {"verification": 1})

    def test_aggregation_defaults_historical_unknown_fields(self) -> None:
        evaluation = build_evaluation_summary(
            [
                {
                    "run_id": "legacy-run",
                    "task_id": "unknown",
                    "product": "unknown",
                    "priority": "unknown",
                    "complexity": "unknown",
                    "status": "completed",
                    "result": "passed",
                    "steps": 0,
                    "observed_steps": 0,
                    "duration_sec": 0,
                }
            ],
            generated_at="2026-05-06T00:00:00+08:00",
        )
        serialized = json.dumps(evaluation, ensure_ascii=False)

        self.assertIn("general", evaluation["by_product"])
        self.assertIn("medium", evaluation["by_priority"])
        self.assertIn("medium", evaluation["by_complexity"])
        self.assertEqual(evaluation["runs"][0]["product"], "general")
        self.assertEqual(evaluation["runs"][0]["priority"], "medium")
        self.assertEqual(evaluation["runs"][0]["complexity"], "medium")
        self.assertEqual(
            evaluation["runs"][0]["completion_signal"],
            "status_passed",
        )
        self.assertNotIn('"unknown"', serialized)

    def test_writes_evaluation_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            output = Path(tmpdir) / "evaluation"
            _write_summary(root, "run-a", {})
            _write_live_artifacts(root / "run-a")

            paths = write_evaluation_report(root, output)
            summary = json.loads(
                Path(paths["evaluation_summary"]).read_text(encoding="utf-8")
            )
            report = Path(paths["evaluation_report"]).read_text(encoding="utf-8")
            dashboard = Path(paths["evaluation_dashboard"]).read_text(encoding="utf-8")
            live_e2e = json.loads(
                Path(paths["live_e2e_evidence"]).read_text(encoding="utf-8")
            )
            live_report = Path(paths["live_e2e_report"]).read_text(encoding="utf-8")

        self.assertEqual(summary["total_runs"], 1)
        self.assertIn("# Feishu Batch Evaluation", report)
        self.assertIn("Action Distribution", report)
        self.assertIn("飞书评测控制台", dashboard)
        self.assertIn("run-a", dashboard)
        self.assertIn("evaluation-data", dashboard)
        self.assertIn("证据完整度", dashboard)
        self.assertEqual(live_e2e["total_runs"], 1)
        self.assertIn("# Feishu Live E2E Evidence", live_report)

    def test_markdown_handles_no_failures(self) -> None:
        markdown = build_evaluation_markdown(
            {
                "generated_at": "2026-05-06T00:00:00+08:00",
                "total_runs": 0,
                "completed_runs": 0,
                "failed_runs": 0,
                "success_rate": 0.0,
                "average_duration_sec": 0.0,
                "average_steps": 0.0,
                "average_observed_steps": 0.0,
                "passed_steps": 0,
                "failed_steps": 0,
                "average_step_pass_rate": None,
                "average_assertion_pass_rate": None,
                "average_screenshot_count": 0.0,
                "average_step_efficiency": None,
                "average_partial_credit": None,
                "average_reflection_count": None,
                "average_redundant_action_rate": None,
                "average_locator_match_rate": None,
                "total_exec_errors": 0,
                "exec_error_runs": 0,
                "artifact_complete_rate": 0.0,
                "by_product": {},
                "by_priority": {},
                "by_complexity": {},
                "action_type_totals": {},
                "completion_signal_counts": {},
                "locator_strategy_totals": {},
                "by_failure_type": {},
                "runs": [],
            }
        )

        self.assertIn("- none", markdown)

    def test_dashboard_html_is_interactive_review_artifact(self) -> None:
        evaluation = build_evaluation_summary(
            [
                {
                    "run_id": "run-a",
                    "task_id": "agentic_im_send_message",
                    "product": "im",
                    "status": "completed",
                    "steps": 2,
                    "passed_steps": 2,
                    "failed_steps": 0,
                    "duration_sec": 1.0,
                    "failure_type": None,
                },
                {
                    "run_id": "run-b",
                    "task_id": "agentic_docs_create_doc",
                    "product": "docs",
                    "status": "failed",
                    "steps": 3,
                    "passed_steps": 1,
                    "failed_steps": 2,
                    "duration_sec": 5.0,
                    "failure_type": "verification",
                },
            ],
            generated_at="2026-05-06T00:00:00+08:00",
        )

        html = build_evaluation_dashboard_html(evaluation)

        self.assertIn("产品覆盖", html)
        self.assertIn("失败分布", html)
        self.assertIn("动作分布", html)
        self.assertIn("任务分布", html)
        self.assertIn("批次健康度", html)
        self.assertIn("证据完整度", html)
        self.assertIn("Step Efficiency", html)
        self.assertIn("Partial Credit", html)
        self.assertIn("Redundant Action", html)
        self.assertIn("定位策略", html)
        self.assertIn("完成信号", html)
        self.assertIn("优先级分组", html)
        self.assertIn("复杂度分组", html)
        self.assertIn("运行明细", html)
        self.assertIn("飞书 Agent 评测控制台", html)
        self.assertIn("--feishu: #1f7aff", html)
        self.assertIn("productFilter", html)
        self.assertIn("scoreboard", html)
        self.assertIn("data-run-id", html)
        self.assertIn("data-run-row", html)
        self.assertIn("compactRunId", html)
        self.assertIn("compactTaskLabel", html)
        self.assertIn("tbody tr.selected", html)
        self.assertIn("renderRunDetail", html)
        self.assertIn("Auto refresh", html)
        self.assertIn("pendingPanel", html)
        self.assertIn("/api/evaluation-summary", html)
        self.assertIn("/runs/${encodeURIComponent(run.run_id)}/${kind}", html)
        self.assertIn("打开报告", html)
        self.assertIn("verification", html)
        self.assertNotIn("bbox", html)
        self.assertNotIn("confidence", html)

    def test_build_live_e2e_evidence_marks_complete_real_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            _write_summary(
                root,
                "run-a",
                {
                    "intent": "agent_s3_feishu",
                    "assertions": [
                        {"name": "message_sent", "passed": True},
                    ],
                },
            )
            _write_live_artifacts(root / "run-a")
            summaries = discover_run_summaries(root)

            evidence = build_live_e2e_evidence(
                summaries,
                generated_at="2026-05-06T00:00:00+08:00",
            )
            markdown = build_live_e2e_markdown(evidence)

        self.assertEqual(evidence["total_runs"], 1)
        self.assertEqual(evidence["artifact_complete_runs"], 1)
        self.assertEqual(evidence["live_e2e_passed_runs"], 1)
        self.assertEqual(evidence["live_e2e_rate"], 1.0)
        self.assertEqual(evidence["runs"][0]["evidence_level"], "live_e2e")
        self.assertTrue(evidence["runs"][0]["checks"]["agent_s3_feishu"])
        self.assertIn("live_e2e_passed `1`", markdown)

    def test_build_live_e2e_evidence_reports_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            _write_summary(
                root,
                "run-a",
                {
                    "intent": "agent_s3_feishu",
                    "assertions": [
                        {"name": "message_sent", "passed": True},
                    ],
                },
            )
            summaries = discover_run_summaries(root)

            evidence = build_live_e2e_evidence(summaries)

        self.assertEqual(evidence["artifact_complete_runs"], 0)
        self.assertEqual(evidence["live_e2e_passed_runs"], 0)
        self.assertFalse(evidence["runs"][0]["artifact_complete"])
        self.assertIn("has_report_md", evidence["runs"][0]["missing"])
        self.assertIn("has_actions_jsonl", evidence["runs"][0]["missing"])
        self.assertIn("has_screenshots", evidence["runs"][0]["missing"])

    def test_cli_writes_report_from_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "runs"
            output = Path(tmpdir) / "evaluation"
            _write_summary(root, "run-a", {})

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_feishu_eval_report.py",
                    "--artifact-root",
                    str(root),
                    "--output-dir",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[3],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("FEISHU_EVALUATION_SUMMARY:", completed.stdout)
        self.assertIn("FEISHU_EVALUATION_DASHBOARD:", completed.stdout)
        self.assertIn("FEISHU_LIVE_E2E_EVIDENCE:", completed.stdout)
        self.assertIn("FEISHU_LIVE_E2E_REPORT:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
