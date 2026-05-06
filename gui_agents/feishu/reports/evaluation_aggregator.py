"""Offline aggregation for Feishu run evaluation artifacts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

_SUCCESS_RESULTS = {"completed", "passed", "success"}
_EMPTY_LABELS = {"", "unknown", "none", "null", "n/a", "-"}
_FIELD_DEFAULTS = {
    "product": "general",
    "task_id": "ad_hoc_task",
    "priority": "medium",
    "complexity": "medium",
    "failure_type": "unclassified_failure",
}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def _safe_number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _optional_average(values: list[Any]) -> float | None:
    numerics = [
        float(value)
        for value in values
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]
    if not numerics:
        return None
    return round(sum(numerics) / len(numerics), 4)


def _success(summary: dict[str, Any]) -> bool:
    result = str(summary.get("result") or "").strip().lower()
    if result:
        return result in _SUCCESS_RESULTS
    status = str(summary.get("status") or "").strip().lower()
    return status in _SUCCESS_RESULTS


def _label(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if text.lower() in _EMPTY_LABELS:
        return default
    return text


def _field_label(summary: dict[str, Any], field: str) -> str:
    return _label(summary.get(field), _FIELD_DEFAULTS.get(field, "not_recorded"))


def _artifact_complete(summary: dict[str, Any]) -> bool:
    manifest = summary.get("artifact_manifest")
    if not isinstance(manifest, dict):
        return False
    screenshot_count = manifest.get(
        "screenshots_count", summary.get("screenshot_count")
    )
    return bool(
        manifest.get("summary")
        and manifest.get("report")
        and manifest.get("actions")
        and _safe_number(screenshot_count) > 0
    )


def _result_from_status(status: Any) -> str:
    normalized = str(status or "not_recorded").strip().lower()
    if normalized in _EMPTY_LABELS:
        return "not_recorded"
    if normalized in _SUCCESS_RESULTS:
        return "passed"
    if normalized in {"failed", "error"}:
        return "failed"
    return normalized or "not_recorded"


def discover_run_summaries(artifact_root: str | Path) -> list[dict[str, Any]]:
    """Load `summary.json` files from immediate run directories."""

    root = Path(artifact_root)
    if not root.exists():
        return []

    summaries: list[dict[str, Any]] = []
    for summary_path in sorted(root.glob("*/summary.json")):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["_summary_path"] = str(summary_path)
            summaries.append(payload)
    return summaries


def _count_by_field(summaries: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for summary in summaries:
        key = _field_label(summary, field)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _success_by_field(
    summaries: list[dict[str, Any]],
    field: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for summary in summaries:
        key = _field_label(summary, field)
        grouped.setdefault(key, []).append(summary)

    output: dict[str, dict[str, Any]] = {}
    for key, items in sorted(grouped.items()):
        completed = sum(1 for item in items if _success(item))
        output[key] = {
            "runs": len(items),
            "completed": completed,
            "failed": len(items) - completed,
            "success_rate": _percent(completed, len(items)),
            "average_duration_sec": round(
                sum(_safe_number(item.get("duration_sec")) for item in items)
                / len(items),
                4,
            ),
            "average_step_pass_rate": _optional_average(
                [item.get("step_pass_rate") for item in items]
            ),
            "average_assertion_pass_rate": _optional_average(
                [item.get("assertion_pass_rate") for item in items]
            ),
            "average_step_efficiency": _optional_average(
                [item.get("step_efficiency") for item in items]
            ),
            "average_partial_credit": _optional_average(
                [item.get("partial_credit") for item in items]
            ),
            "average_reflection_count": _optional_average(
                [item.get("reflection_count") for item in items]
            ),
            "average_redundant_action_rate": _optional_average(
                [item.get("redundant_action_rate") for item in items]
            ),
            "average_locator_match_rate": _optional_average(
                [_locator_match_rate(item) for item in items]
            ),
            "total_exec_errors": int(
                sum(_safe_number(item.get("exec_error_count")) for item in items)
            ),
            "average_screenshot_count": round(
                sum(_safe_number(item.get("screenshot_count")) for item in items)
                / len(items),
                4,
            ),
        }
    return output


def _action_type_totals(summaries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for summary in summaries:
        action_counts = summary.get("action_type_counts")
        if not isinstance(action_counts, dict):
            continue
        for action, value in action_counts.items():
            counts[str(action)] = counts.get(str(action), 0) + int(_safe_number(value))
    return dict(sorted(counts.items()))


def _completion_signal_counts(summaries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for summary in summaries:
        signal = _label(
            summary.get("completion_signal"),
            f"status_{_result_from_status(summary.get('status'))}",
        )
        counts[signal] = counts.get(signal, 0) + 1
    return dict(sorted(counts.items()))


def _locator_match_rate(summary: dict[str, Any]) -> float | None:
    locator_stats = summary.get("locator_stats")
    if not isinstance(locator_stats, dict):
        return None
    value = locator_stats.get("match_rate")
    return float(value) if isinstance(value, int | float) else None


def _locator_strategy_totals(summaries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for summary in summaries:
        locator_stats = summary.get("locator_stats")
        if not isinstance(locator_stats, dict):
            continue
        strategy_counts = locator_stats.get("strategy_counts")
        if not isinstance(strategy_counts, dict):
            continue
        for strategy, value in strategy_counts.items():
            counts[str(strategy)] = counts.get(str(strategy), 0) + int(
                _safe_number(value)
            )
    return dict(sorted(counts.items()))


def build_evaluation_summary(
    summaries: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build aggregate evaluation facts from per-run summaries."""

    total_runs = len(summaries)
    completed_runs = sum(1 for summary in summaries if _success(summary))
    failed_runs = total_runs - completed_runs
    durations = [_safe_number(summary.get("duration_sec")) for summary in summaries]
    steps = [_safe_number(summary.get("steps")) for summary in summaries]
    observed_steps = [
        _safe_number(summary.get("observed_steps", summary.get("steps")))
        for summary in summaries
    ]
    passed_steps = sum(
        int(_safe_number(summary.get("passed_steps"))) for summary in summaries
    )
    failed_steps = sum(
        int(_safe_number(summary.get("failed_steps"))) for summary in summaries
    )
    step_pass_rates = [summary.get("step_pass_rate") for summary in summaries]
    assertion_pass_rates = [summary.get("assertion_pass_rate") for summary in summaries]
    screenshot_counts = [
        _safe_number(summary.get("screenshot_count")) for summary in summaries
    ]
    step_efficiencies = [summary.get("step_efficiency") for summary in summaries]
    partial_credits = [summary.get("partial_credit") for summary in summaries]
    reflection_counts = [summary.get("reflection_count") for summary in summaries]
    redundant_action_rates = [
        summary.get("redundant_action_rate") for summary in summaries
    ]
    locator_match_rates = [_locator_match_rate(summary) for summary in summaries]
    exec_error_counts = [
        _safe_number(summary.get("exec_error_count")) for summary in summaries
    ]
    artifact_complete_runs = sum(
        1 for summary in summaries if _artifact_complete(summary)
    )
    by_product = _success_by_field(summaries, "product")
    by_task = _success_by_field(summaries, "task_id")
    by_priority = _success_by_field(summaries, "priority")
    by_complexity = _success_by_field(summaries, "complexity")

    return {
        "generated_at": generated_at or _now_iso(),
        "total_runs": total_runs,
        "successful_runs": completed_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "success_rate": _percent(completed_runs, total_runs),
        "average_duration_sec": (
            round(sum(durations) / total_runs, 3) if total_runs else 0.0
        ),
        "average_steps": round(sum(steps) / total_runs, 3) if total_runs else 0.0,
        "average_observed_steps": (
            round(sum(observed_steps) / total_runs, 3) if total_runs else 0.0
        ),
        "passed_steps": passed_steps,
        "failed_steps": failed_steps,
        "average_step_pass_rate": _optional_average(step_pass_rates),
        "average_assertion_pass_rate": _optional_average(assertion_pass_rates),
        "average_screenshot_count": (
            round(sum(screenshot_counts) / total_runs, 3) if total_runs else 0.0
        ),
        "average_step_efficiency": _optional_average(step_efficiencies),
        "average_partial_credit": _optional_average(partial_credits),
        "average_reflection_count": _optional_average(reflection_counts),
        "average_redundant_action_rate": _optional_average(redundant_action_rates),
        "average_locator_match_rate": _optional_average(locator_match_rates),
        "total_exec_errors": int(sum(exec_error_counts)),
        "exec_error_runs": sum(1 for value in exec_error_counts if value > 0),
        "artifact_complete_runs": artifact_complete_runs,
        "artifact_complete_rate": _percent(artifact_complete_runs, total_runs),
        "action_type_totals": _action_type_totals(summaries),
        "completion_signal_counts": _completion_signal_counts(summaries),
        "locator_strategy_totals": _locator_strategy_totals(summaries),
        "by_product": by_product,
        "by_task": by_task,
        "by_priority": by_priority,
        "by_complexity": by_complexity,
        "by_failure_type": _count_by_field(
            [summary for summary in summaries if not _success(summary)],
            "failure_type",
        ),
        "coverage": {
            "products": len(by_product),
            "tasks": len(by_task),
        },
        "runs": [
            {
                "run_id": summary.get("run_id"),
                "task_id": _field_label(summary, "task_id"),
                "product": _field_label(summary, "product"),
                "priority": _field_label(summary, "priority"),
                "complexity": _field_label(summary, "complexity"),
                "status": summary.get("status"),
                "result": summary.get("result")
                or _result_from_status(summary.get("status")),
                "failure_type": summary.get("failure_type"),
                "failure_reason": summary.get("failure_reason"),
                "duration_sec": summary.get("duration_sec"),
                "observed_steps": summary.get("observed_steps", summary.get("steps")),
                "step_pass_rate": summary.get("step_pass_rate"),
                "step_efficiency": summary.get("step_efficiency"),
                "partial_credit": summary.get("partial_credit"),
                "assertion_pass_rate": summary.get("assertion_pass_rate"),
                "screenshot_count": summary.get("screenshot_count", 0),
                "reflection_count": summary.get("reflection_count"),
                "redundant_action_rate": summary.get("redundant_action_rate"),
                "locator_stats": summary.get("locator_stats"),
                "completion_signal": _label(
                    summary.get("completion_signal"),
                    f"status_{_result_from_status(summary.get('status'))}",
                ),
                "exec_error_count": summary.get("exec_error_count", 0),
                "exec_errors": summary.get("exec_errors", []),
                "action_type_counts": summary.get("action_type_counts", {}),
                "artifact_complete": _artifact_complete(summary),
                "report_path": (
                    summary.get("artifact_manifest", {}).get("report")
                    if isinstance(summary.get("artifact_manifest"), dict)
                    else None
                ),
                "final_screenshot": (
                    summary.get("artifact_manifest", {}).get("final_screenshot")
                    if isinstance(summary.get("artifact_manifest"), dict)
                    else None
                ),
                "summary_path": summary.get("_summary_path"),
            }
            for summary in summaries
        ],
    }


def build_evaluation_markdown(evaluation: dict[str, Any]) -> str:
    """Build a human-readable batch evaluation report."""

    def _display_percent(value: Any) -> str:
        if not isinstance(value, int | float):
            return "-"
        return f"{float(value) * 100:.1f}%"

    lines = [
        "# Feishu Batch Evaluation",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Generated At | `{evaluation.get('generated_at')}` |",
        f"| Total Runs | `{evaluation.get('total_runs')}` |",
        f"| Successful Runs | `{evaluation.get('successful_runs', evaluation.get('completed_runs'))}` |",
        f"| Failed Runs | `{evaluation.get('failed_runs')}` |",
        f"| Success Rate | `{_display_percent(evaluation.get('success_rate'))}` |",
        f"| Average Duration (s) | `{evaluation.get('average_duration_sec')}` |",
        f"| Average Planned Steps | `{evaluation.get('average_steps')}` |",
        f"| Average Observed Steps | `{evaluation.get('average_observed_steps')}` |",
        f"| Average Step Pass Rate | `{_display_percent(evaluation.get('average_step_pass_rate'))}` |",
        f"| Average Assertion Pass Rate | `{_display_percent(evaluation.get('average_assertion_pass_rate'))}` |",
        f"| Average Screenshot Count | `{evaluation.get('average_screenshot_count')}` |",
        f"| Average Step Efficiency | `{_display_percent(evaluation.get('average_step_efficiency'))}` |",
        f"| Average Partial Credit | `{_display_percent(evaluation.get('average_partial_credit'))}` |",
        f"| Average Reflection Count | `{evaluation.get('average_reflection_count')}` |",
        f"| Average Redundant Action Rate | `{_display_percent(evaluation.get('average_redundant_action_rate'))}` |",
        f"| Average Locator Match Rate | `{_display_percent(evaluation.get('average_locator_match_rate'))}` |",
        f"| Total Exec Errors | `{evaluation.get('total_exec_errors')}` |",
        f"| Artifact Complete Rate | `{_display_percent(evaluation.get('artifact_complete_rate'))}` |",
        f"| Passed Steps | `{evaluation.get('passed_steps')}` |",
        f"| Failed Steps | `{evaluation.get('failed_steps')}` |",
        "",
        "## By Product",
        "",
        "| Product | Runs | Passed | Failed | Success Rate | Avg Duration | Avg Step Pass | Avg Assertion Pass | Avg Step Efficiency | Avg Screenshots |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for product, item in evaluation.get("by_product", {}).items():
        lines.append(
            f"| `{product}` | `{item['runs']}` | `{item['completed']}` | "
            f"`{item['failed']}` | `{_display_percent(item['success_rate'])}` | "
            f"`{item.get('average_duration_sec')}` | "
            f"`{_display_percent(item.get('average_step_pass_rate'))}` | "
            f"`{_display_percent(item.get('average_assertion_pass_rate'))}` | "
            f"`{_display_percent(item.get('average_step_efficiency'))}` | "
            f"`{item.get('average_screenshot_count')}` |"
        )

    for title, key in (
        ("By Priority", "by_priority"),
        ("By Complexity", "by_complexity"),
    ):
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| Group | Runs | Passed | Failed | Success Rate | Avg Partial Credit | Avg Step Efficiency | Avg Redundant Action | Exec Errors |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        groups = evaluation.get(key, {})
        if groups:
            for group, item in groups.items():
                lines.append(
                    f"| `{group}` | `{item['runs']}` | `{item['completed']}` | "
                    f"`{item['failed']}` | `{_display_percent(item['success_rate'])}` | "
                    f"`{_display_percent(item.get('average_partial_credit'))}` | "
                    f"`{_display_percent(item.get('average_step_efficiency'))}` | "
                    f"`{_display_percent(item.get('average_redundant_action_rate'))}` | "
                    f"`{item.get('total_exec_errors')}` |"
                )
        else:
            lines.append("| none | `0` | `0` | `0` | `-` | `-` | `-` | `-` | `0` |")

    lines.extend(["", "## Action Distribution", "", "| Action | Count |", "|---|---:|"])
    action_totals = evaluation.get("action_type_totals", {})
    if action_totals:
        for action, count in action_totals.items():
            lines.append(f"| `{action}` | `{count}` |")
    else:
        lines.append("| none | `0` |")

    lines.extend(
        [
            "",
            "## Locator Strategy Distribution",
            "",
            "| Strategy | Count |",
            "|---|---:|",
        ]
    )
    locator_totals = evaluation.get("locator_strategy_totals", {})
    if locator_totals:
        for strategy, count in locator_totals.items():
            lines.append(f"| `{strategy}` | `{count}` |")
    else:
        lines.append("| none | `0` |")

    lines.extend(
        [
            "",
            "## Completion Signals",
            "",
            "| Signal | Count |",
            "|---|---:|",
        ]
    )
    completion_totals = evaluation.get("completion_signal_counts", {})
    if completion_totals:
        for signal, count in completion_totals.items():
            lines.append(f"| `{signal}` | `{count}` |")
    else:
        lines.append("| none | `0` |")

    lines.extend(["", "## By Failure Type"])
    failure_types = evaluation.get("by_failure_type", {})
    if failure_types:
        lines.extend(["", "| Failure Type | Count |", "|---|---:|"])
        for failure_type, count in failure_types.items():
            lines.append(f"| `{failure_type}` | `{count}` |")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Runs",
            "",
            "| Run | Task | Product | Result | Duration | Observed Steps | Assertion Pass | Screenshots | Artifact Complete |",
            "|---|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for run in evaluation.get("runs", []):
        lines.append(
            f"| `{run.get('run_id')}` | `{run.get('task_id')}` | "
            f"`{run.get('product')}` | `{run.get('result')}` | "
            f"`{run.get('duration_sec')}` | `{run.get('observed_steps')}` | "
            f"`{_display_percent(run.get('assertion_pass_rate'))}` | "
            f"`{run.get('screenshot_count')}` | `{run.get('artifact_complete')}` |"
        )
    return "\n".join(lines) + "\n"


def _json_for_script(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return payload.replace("</", "<\\/")


def build_evaluation_dashboard_html(evaluation: dict[str, Any]) -> str:
    """Build a self-contained interactive HTML evaluation dashboard."""

    payload = _json_for_script(evaluation)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>飞书评测控制台</title>
  <style>
    :root {{
      --page: #f5f8ff;
      --paper: #ffffff;
      --ink: #142033;
      --muted: #64748b;
      --line: rgba(47, 111, 235, 0.12);
      --feishu: #1f7aff;
      --feishu-deep: #1456d9;
      --cyan: #00b8d9;
      --success: #12b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --soft-blue: #eaf2ff;
      --soft-cyan: #e7fbff;
      --radius: 12px;
      --shadow-sm: 0 1px 3px rgba(20, 64, 153, 0.08);
      --shadow: 0 4px 16px rgba(20, 64, 153, 0.08), 0 1px 4px rgba(20, 64, 153, 0.06);
      --shadow-lg: 0 12px 32px rgba(20, 64, 153, 0.1), 0 2px 8px rgba(20, 64, 153, 0.06);
      --body-font: "Microsoft YaHei UI", "Aptos", "Segoe UI Variable Text", sans-serif;
      --mono-font: "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background: linear-gradient(180deg, #fafcff 0%, var(--page) 40%, #f0f4ff 100%);
      font-family: var(--body-font);
      -webkit-font-smoothing: antialiased;
    }}

    .shell {{
      width: min(1200px, calc(100vw - 40px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }}

    .hero {{
      position: relative;
      overflow: hidden;
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 32px;
      align-items: start;
      padding: 36px 40px;
      border-radius: var(--radius);
      background: linear-gradient(135deg, #ffffff 0%, #f6f9ff 100%);
      border: 1px solid rgba(31, 122, 255, 0.1);
      box-shadow: var(--shadow-lg);
    }}

    .hero::before {{
      content: "";
      position: absolute;
      top: 0; left: 0;
      width: 4px;
      height: 64px;
      background: linear-gradient(180deg, var(--feishu), var(--cyan));
      border-radius: 0 0 4px 0;
    }}

    .eyebrow {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      width: fit-content;
      padding: 5px 12px;
      border: 1px solid rgba(31, 122, 255, 0.15);
      border-radius: 999px;
      color: var(--feishu-deep);
      background: var(--soft-blue);
      font-size: 0.78rem;
      font-weight: 500;
      letter-spacing: 0.02em;
    }}

    h1 {{
      max-width: 780px;
      margin: 20px 0 8px;
      color: var(--ink);
      font-size: clamp(1.8rem, 4vw, 2.6rem);
      font-weight: 700;
      line-height: 1.15;
      letter-spacing: -0.01em;
    }}

    .hero p {{
      max-width: 760px;
      margin: 0;
      color: var(--muted);
      font-size: 0.94rem;
      line-height: 1.65;
    }}

    .hero-links,
    .detail-actions,
    .table-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}

    .hero-links {{ margin-top: 20px; }}

    .live-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}

    .live-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 30px;
      padding: 5px 10px;
      border-radius: 999px;
      color: var(--feishu-deep);
      background: rgba(31, 122, 255, 0.08);
      border: 1px solid rgba(31, 122, 255, 0.12);
      font-size: 0.78rem;
      font-weight: 600;
    }}

    .hero-link,
    .detail-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      min-height: 36px;
      border: 1px solid rgba(31, 122, 255, 0.18);
      border-radius: 999px;
      padding: 6px 16px;
      color: var(--feishu-deep);
      background: #ffffff;
      font-size: 0.82rem;
      font-weight: 500;
      text-decoration: none;
      transition: all 180ms ease;
    }}

    .hero-link:hover,
    .detail-link:hover {{
      color: #ffffff;
      background: var(--feishu);
      border-color: var(--feishu);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(31, 122, 255, 0.25);
    }}

    .stamp {{
      align-self: start;
      justify-self: end;
      z-index: 1;
      width: min(240px, 100%);
      padding: 20px 24px;
      border-radius: var(--radius);
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid rgba(31, 122, 255, 0.08);
      color: var(--muted);
      font-size: 0.82rem;
      box-shadow: var(--shadow-sm);
    }}

    .stamp strong {{
      display: block;
      margin-top: 8px;
      color: var(--feishu-deep);
      font-family: var(--mono-font);
      font-size: 1.35rem;
      font-weight: 600;
    }}

    .stamp small {{
      display: block;
      margin-top: 4px;
      font-family: var(--mono-font);
      font-size: 0.78rem;
    }}

    .metrics {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}

    .quality-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}

    .metric,
    .quality-card {{
      padding: 20px 22px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow);
      transition: box-shadow 200ms ease, transform 200ms ease;
    }}

    .metric:hover,
    .quality-card:hover {{
      box-shadow: var(--shadow-lg);
      transform: translateY(-2px);
    }}

    .metric {{
      position: relative;
      overflow: hidden;
    }}

    .metric::before {{
      content: "";
      position: absolute;
      top: 0; left: 0;
      width: 3px;
      height: 100%;
      background: linear-gradient(180deg, var(--feishu), var(--cyan));
      border-radius: 3px 0 0 3px;
    }}

    .metric label {{
      display: block;
      color: var(--muted);
      font-size: 0.75rem;
      font-weight: 500;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}

    .metric b {{
      display: block;
      margin-top: 10px;
      color: var(--ink);
      font-size: clamp(1.6rem, 3vw, 2.4rem);
      font-weight: 700;
      line-height: 1;
      letter-spacing: -0.01em;
    }}

    .metric small {{
      display: block;
      margin-top: 8px;
      color: var(--feishu-deep);
      font-size: 0.8rem;
    }}

    .quality-card {{
      position: relative;
      overflow: hidden;
    }}

    .quality-card::before {{
      content: "";
      position: absolute;
      top: 0; left: 0;
      width: 3px;
      height: 100%;
      background: linear-gradient(180deg, var(--cyan), var(--success));
      border-radius: 3px 0 0 3px;
    }}

    .quality-card label {{
      display: block;
      color: var(--muted);
      font-size: 0.75rem;
      font-weight: 500;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}

    .quality-card b {{
      display: block;
      margin: 10px 0 6px;
      color: var(--ink);
      font-size: 1.6rem;
      font-weight: 700;
      line-height: 1;
    }}

    .quality-card small {{
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.45;
    }}

    .filters {{
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      align-items: end;
      justify-content: space-between;
      margin: 24px 0;
      padding: 16px 20px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow);
    }}

    .pending-panel {{
      display: grid;
      gap: 12px;
      margin: 0 0 24px;
      padding: 18px 20px;
      border-radius: var(--radius);
      background: linear-gradient(135deg, #fff8ec 0%, #ffffff 100%);
      border: 1px solid rgba(245, 158, 11, 0.2);
      box-shadow: var(--shadow-sm);
    }}

    .pending-panel[hidden] {{
      display: none;
    }}

    .pending-panel h2 {{
      margin: 0;
      color: #9a5b00;
      font-size: 1rem;
      font-weight: 700;
    }}

    .pending-panel p {{
      margin: 0;
      color: #8b6b30;
      font-size: 0.88rem;
      line-height: 1.6;
    }}

    .pending-list {{
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}

    .pending-item {{
      padding: 12px 14px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(245, 158, 11, 0.14);
    }}

    .pending-item strong {{
      display: block;
      color: var(--ink);
      font-family: var(--mono-font);
      font-size: 0.9rem;
    }}

    .pending-item span {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.5;
    }}

    .filters label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 0.73rem;
      font-weight: 500;
      letter-spacing: 0.02em;
    }}

    select,
    input {{
      min-width: 150px;
      border: 1px solid rgba(31, 122, 255, 0.16);
      border-radius: 8px;
      padding: 9px 12px;
      color: var(--ink);
      background: #ffffff;
      font: inherit;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 180ms ease, box-shadow 180ms ease;
    }}

    select:focus,
    input:focus {{
      border-color: var(--feishu);
      box-shadow: 0 0 0 3px rgba(31, 122, 255, 0.1);
    }}

    input {{ min-width: min(320px, 70vw); }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-top: 24px;
    }}

    .card,
    .table-panel {{
      padding: 24px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow);
    }}

    .scoreboard {{
      display: grid;
      grid-template-columns: 1.05fr 0.95fr 0.95fr;
      gap: 16px;
      margin: 24px 0;
    }}

    .score-card {{
      position: relative;
      overflow: hidden;
      padding: 24px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow);
    }}

    .score-card::after {{
      content: "";
      position: absolute;
      right: 0;
      bottom: 0;
      width: 80px;
      height: 4px;
      border-radius: 4px 0 0 0;
      background: linear-gradient(90deg, var(--feishu), var(--cyan));
    }}

    .score-card label {{
      display: block;
      color: var(--muted);
      font-size: 0.75rem;
      font-weight: 500;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}

    .score-card strong {{
      display: block;
      margin: 10px 0 6px;
      color: var(--feishu-deep);
      font-size: clamp(2rem, 4vw, 3.2rem);
      font-weight: 700;
      line-height: 1;
      letter-spacing: -0.01em;
    }}

    .score-card p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.5;
    }}

    .health-band {{
      display: grid;
      grid-template-columns: var(--completed, 0fr) var(--failed, 0fr);
      overflow: hidden;
      height: 14px;
      margin-top: 16px;
      border-radius: 999px;
      background: rgba(31, 122, 255, 0.08);
    }}

    .health-band i:first-child {{
      background: linear-gradient(90deg, var(--feishu), var(--cyan));
    }}

    .health-band i:last-child {{
      background: linear-gradient(90deg, var(--danger), var(--warning));
    }}

    .section-title {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }}

    .section-title h2 {{
      margin: 0;
      color: var(--ink);
      font-size: 1.1rem;
      font-weight: 600;
    }}

    .section-title span {{
      color: var(--muted);
      font-size: 0.75rem;
    }}

    .product-row,
    .failure-row,
    .task-row,
    .action-row,
    .group-row,
    .locator-row,
    .completion-row {{
      display: grid;
      grid-template-columns: 120px 1fr 72px;
      gap: 12px;
      align-items: center;
      padding: 10px 0;
      border-top: 1px solid rgba(31, 122, 255, 0.06);
    }}

    .product-row strong,
    .failure-row strong,
    .task-row strong,
    .action-row strong,
    .group-row strong,
    .locator-row strong,
    .completion-row strong {{
      font-size: 0.88rem;
      font-weight: 500;
    }}

    .bar {{
      overflow: hidden;
      height: 12px;
      border-radius: 999px;
      background: rgba(31, 122, 255, 0.06);
    }}

    .bar i {{
      display: block;
      width: var(--value);
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--feishu), var(--cyan));
      transition: width 400ms ease;
    }}

    .failure-row .bar i {{
      background: linear-gradient(90deg, var(--danger), var(--warning));
    }}

    .task-row .bar i {{
      background: linear-gradient(90deg, var(--feishu-deep), var(--feishu));
    }}

    .action-row .bar i {{
      background: linear-gradient(90deg, var(--cyan), var(--success));
    }}

    .locator-row .bar i {{
      background: linear-gradient(90deg, var(--feishu), var(--success));
    }}

    .completion-row .bar i,
    .group-row .bar i {{
      background: linear-gradient(90deg, var(--feishu-deep), var(--cyan));
    }}

    .table-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 16px;
      margin-top: 24px;
      align-items: start;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}

    th,
    td {{
      padding: 10px 10px;
      border-top: 1px solid rgba(31, 122, 255, 0.06);
      text-align: left;
      vertical-align: middle;
    }}

    th {{
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      background: rgba(234, 242, 255, 0.5);
      position: sticky;
      top: 0;
    }}

    tbody tr {{
      cursor: pointer;
      transition: background 140ms ease;
    }}

    tbody tr:hover {{
      background: rgba(31, 122, 255, 0.04);
    }}

    tbody tr.selected {{
      background: rgba(31, 122, 255, 0.07);
      box-shadow: inset 3px 0 0 var(--feishu);
    }}

    .run-id {{
      display: inline-flex;
      align-items: center;
      color: var(--feishu-deep);
      font-family: var(--mono-font);
      font-size: 0.85rem;
      font-weight: 600;
    }}

    .compact-label {{
      display: inline-block;
      max-width: 20ch;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      vertical-align: bottom;
    }}

    .pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 72px;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 0.73rem;
      font-weight: 500;
    }}

    .row-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(31, 122, 255, 0.18);
      border-radius: 999px;
      padding: 5px 12px;
      color: var(--feishu-deep);
      background: var(--soft-blue);
      font-size: 0.75rem;
      font-weight: 500;
      cursor: pointer;
      text-decoration: none;
      transition: all 160ms ease;
    }}

    .row-button:hover {{
      color: #ffffff;
      background: var(--feishu);
      border-color: var(--feishu);
      box-shadow: 0 2px 8px rgba(31, 122, 255, 0.2);
    }}

    .run-detail {{
      position: sticky;
      top: 24px;
      padding: 24px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow);
    }}

    .run-detail h3 {{
      margin: 0 0 12px;
      color: var(--ink);
      font-size: 1.15rem;
      font-weight: 600;
    }}

    .detail-line {{
      display: grid;
      gap: 3px;
      padding: 10px 0;
      border-top: 1px solid rgba(31, 122, 255, 0.06);
    }}

    .detail-line span {{
      color: var(--muted);
      font-size: 0.7rem;
      font-weight: 500;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}

    .detail-line b {{
      color: var(--ink);
      font-size: 0.88rem;
      word-break: break-word;
    }}

    .completed {{
      color: #065f46;
      background: rgba(18, 185, 129, 0.12);
    }}

    .failed {{
      color: #9f1239;
      background: rgba(239, 68, 68, 0.12);
    }}

    .empty {{
      padding: 32px 24px;
      text-align: center;
      color: var(--muted);
      font-size: 0.88rem;
      border-radius: 8px;
      background: rgba(234, 242, 255, 0.5);
      border: 1px solid rgba(31, 122, 255, 0.06);
    }}

    @media (max-width: 900px) {{
      .hero {{
        grid-template-columns: 1fr;
        padding: 28px;
      }}

      .stamp {{
        justify-self: start;
        width: 100%;
      }}

      .metrics {{
        grid-template-columns: repeat(3, 1fr);
      }}

      .quality-grid {{
        grid-template-columns: repeat(2, 1fr);
      }}

      .scoreboard {{
        grid-template-columns: 1fr;
      }}

      .grid {{
        grid-template-columns: 1fr;
      }}

      .table-grid {{
        grid-template-columns: 1fr;
      }}

      .table-wrap {{
        overflow-x: auto;
      }}
    }}

    @media (max-width: 560px) {{
      .shell {{ width: min(100vw - 24px, 1200px); padding-top: 20px; }}
      .hero {{ padding: 20px; }}
      .metrics {{ grid-template-columns: 1fr 1fr; }}
      .quality-grid {{ grid-template-columns: 1fr; }}
      .filters {{ flex-direction: column; align-items: stretch; }}
      select,
      input {{ width: 100%; min-width: 0; }}
      .product-row,
      .failure-row,
      .task-row,
      .action-row,
      .group-row,
      .locator-row,
      .completion-row {{
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <div class="eyebrow">Feishu GUI Agent / 评测看板</div>
        <h1>飞书 Agent 评测控制台</h1>
        <p>
          面向 AgentS3 的离线评测审阅页。聚合批量运行质量、证据完整度、
          失败类型和单次运行明细，保持静态审阅，不进入 runtime 执行路径。
        </p>
        <div class="hero-links" aria-label="报告入口">
          <a class="hero-link" href="/artifacts/evaluation/evaluation_report.md">批次 Markdown</a>
          <a class="hero-link" href="/artifacts/evaluation/live_e2e_evidence.md">Live E2E 证据</a>
          <a class="hero-link" href="/artifacts/evaluation/evaluation_summary.json">评测 JSON</a>
        </div>
        <div class="live-strip" aria-label="dashboard live state">
          <span class="live-chip" id="refreshStatus">Auto refresh: checking</span>
          <span class="live-chip" id="pendingCount">Pending runs: 0</span>
        </div>
      </div>
      <aside class="stamp">
        <span>生成时间</span>
        <strong id="generatedDate">-</strong>
        <small id="generatedTime">-</small>
      </aside>
    </section>

    <section class="metrics" id="metrics"></section>

    <section class="scoreboard" id="scoreboard" aria-label="评测洞察"></section>

    <section class="quality-grid" id="qualityMetrics" aria-label="过程质量"></section>

    <section class="filters" aria-label="运行筛选">
      <label>
        产品
        <select id="productFilter"></select>
      </label>
      <label>
        结果
        <select id="statusFilter">
          <option value="all">全部</option>
          <option value="passed">通过</option>
          <option value="failed">失败</option>
        </select>
      </label>
      <label>
        失败类型
        <select id="failureFilter"></select>
      </label>
      <label>
        搜索
        <input id="searchFilter" type="search" placeholder="运行 ID 或任务 ID">
      </label>
    </section>

    <section class="pending-panel" id="pendingPanel" hidden></section>

    <section class="grid">
      <article class="card">
        <div class="section-title">
          <h2>产品覆盖</h2>
          <span>按产品统计通过率</span>
        </div>
        <div id="productCards"></div>
      </article>

      <article class="card">
        <div class="section-title">
          <h2>动作分布</h2>
          <span>批次动作总量</span>
        </div>
        <div id="actionMix"></div>
      </article>

      <article class="card">
        <div class="section-title">
          <h2>定位策略</h2>
          <span>locator 使用统计</span>
        </div>
        <div id="locatorMix"></div>
      </article>

      <article class="card">
        <div class="section-title">
          <h2>完成信号</h2>
          <span>agent 终态来源</span>
        </div>
        <div id="completionMix"></div>
      </article>

      <article class="card">
        <div class="section-title">
          <h2>优先级分组</h2>
          <span>按 priority 统计</span>
        </div>
        <div id="priorityMix"></div>
      </article>

      <article class="card">
        <div class="section-title">
          <h2>复杂度分组</h2>
          <span>按 complexity 统计</span>
        </div>
        <div id="complexityMix"></div>
      </article>

      <article class="card">
        <div class="section-title">
          <h2>失败分布</h2>
          <span>仅统计失败运行</span>
        </div>
        <div id="failureMix"></div>
      </article>

      <article class="card">
        <div class="section-title">
          <h2>任务分布</h2>
          <span>运行集中度</span>
        </div>
        <div id="taskMix"></div>
      </article>
    </section>

    <section class="table-grid">
      <article class="table-panel">
        <div class="section-title">
          <h2>运行列表</h2>
          <span id="runCount">0 条可见</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>运行</th>
                <th>任务</th>
                <th>产品</th>
                <th>状态</th>
                <th>失败</th>
                <th>耗时</th>
                <th>步数</th>
                <th>断言</th>
                <th>截图</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="runsTable"></tbody>
          </table>
        </div>
      </article>

      <aside class="run-detail" id="runDetail" aria-label="选中运行明细">
        <h3>运行明细</h3>
        <p class="empty">选择一条运行记录查看聚合事实。</p>
      </aside>
    </section>
  </main>

  <script id="evaluation-data" type="application/json">{payload}</script>
  <script>
    let evaluation = JSON.parse(
      document.getElementById("evaluation-data").textContent
    );
    let dashboardSnapshotId = evaluation.dashboard_snapshot_id || null;
    let dashboardRefreshTimer = null;
    const DASHBOARD_API_URL = "/api/evaluation-summary";
    const DASHBOARD_POLL_MS = 5000;

    const $ = (selector) => document.querySelector(selector);
    const productFilter = $("#productFilter");
    const failureFilter = $("#failureFilter");
    const statusFilter = $("#statusFilter");
    const searchFilter = $("#searchFilter");

    function setRefreshStatus(message) {{
      const node = $("#refreshStatus");
      if (node) {{
        node.textContent = message;
      }}
    }}

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function percent(value) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) {{
        return "-";
      }}
      return `${{Math.round(Number(value || 0) * 1000) / 10}}%`;
    }}

    function duration(value) {{
      const numeric = Number(value || 0);
      return `${{numeric.toFixed(numeric >= 10 ? 1 : 2)}} 秒`;
    }}

    function option(value, label) {{
      return `<option value="${{escapeHtml(value)}}">${{escapeHtml(label)}}</option>`;
    }}

    function runPath(run, kind) {{
      if (!run || !run.run_id) {{
        return "#";
      }}
      return `/runs/${{encodeURIComponent(run.run_id)}}/${{kind}}`;
    }}

    function compactRunId(runId) {{
      const text = String(runId || "ad_hoc_run");
      const parts = text.split("_").filter(Boolean);
      return parts.length ? parts[parts.length - 1] : text;
    }}

    function compactTaskLabel(taskId) {{
      const text = String(taskId || "-");
      const normalized = text
        .replace(/^agentic_/, "")
        .replace(/^tc_/, "")
        .replaceAll("_", " ");
      return normalized.length > 24 ? `${{normalized.slice(0, 21)}}...` : normalized;
    }}

    function initGeneratedAt() {{
      const parsed = new Date(evaluation.generated_at || "");
      if (Number.isNaN(parsed.getTime())) {{
        $("#generatedDate").textContent = "未记录";
        $("#generatedTime").textContent = "-";
        return;
      }}
      $("#generatedDate").textContent = parsed.toLocaleDateString("zh-CN");
      $("#generatedTime").textContent = parsed.toLocaleTimeString("zh-CN");
    }}

    function initFilters() {{
      const products = Object.keys(evaluation.by_product || {{}});
      const failures = Object.keys(evaluation.by_failure_type || {{}});
      productFilter.innerHTML = option("all", "全部") +
        products.map((item) => option(item, item)).join("");
      failureFilter.innerHTML = option("all", "全部") +
        option("__none__", "无失败") +
        failures.map((item) => option(item, item)).join("");
    }}

    function renderPendingPanel() {{
      const pendingRuns = Array.isArray(evaluation.pending_runs)
        ? evaluation.pending_runs
        : [];
      const panel = $("#pendingPanel");
      const countNode = $("#pendingCount");
      if (countNode) {{
        countNode.textContent = `Pending runs: ${{pendingRuns.length}}`;
      }}
      if (!panel) {{
        return;
      }}
      if (!pendingRuns.length) {{
        panel.hidden = true;
        panel.innerHTML = "";
        return;
      }}
      panel.hidden = false;
      panel.innerHTML = `
        <div class="section-title">
          <h2>Pending Runs</h2>
          <span>${{escapeHtml(String(pendingRuns.length))}} artifact directories without summary.json</span>
        </div>
        <p>
          These runs already have partial artifacts on disk, but they have not produced
          <code>summary.json</code> yet, so they are not included in the main run table.
        </p>
        <div class="pending-list">
          ${{
            pendingRuns.slice(0, 6).map((run) => `
              <article class="pending-item">
                <strong>${{escapeHtml(run.run_id || "pending_run")}}</strong>
                <span>
                  screenshots=${{escapeHtml(run.screenshot_count ?? 0)}} ·
                  artifacts=${{escapeHtml((run.present_artifacts || []).join(", ") || "partial")}}
                </span>
                <span>
                  missing=${{escapeHtml((run.missing_artifacts || []).join(", ") || "not_recorded")}}
                </span>
              </article>
            `).join("")
          }}
        </div>
      `;
    }}

    function renderMetrics() {{
      const metrics = [
        ["运行总数", evaluation.total_runs || 0, "已收集 summary"],
        ["通过率", percent(evaluation.success_rate), "通过 / 总数"],
        ["平均耗时", duration(evaluation.average_duration_sec), "单次运行"],
        ["平均观测步数", evaluation.average_observed_steps || 0, "runtime 轨迹深度"],
        ["断言通过率", percent(evaluation.average_assertion_pass_rate), "最终校验结果"],
        ["平均截图数", evaluation.average_screenshot_count || 0, "证据体量"],
      ];
      $("#metrics").innerHTML = metrics.map(([label, value, hint]) => `
        <article class="metric">
          <label>${{escapeHtml(label)}}</label>
          <b>${{escapeHtml(value)}}</b>
          <small>${{escapeHtml(hint)}}</small>
        </article>
      `).join("");
    }}

    function renderQualityMetrics() {{
      const metrics = [
        ["Step Efficiency", percent(evaluation.average_step_efficiency), "估计步数 / 观测步数，越高越少绕路"],
        ["Partial Credit", percent(evaluation.average_partial_credit), "失败时保留阶段性完成度"],
        ["Reflection", evaluation.average_reflection_count ?? "-", "平均反思次数，观察自愈介入"],
        ["Redundant Action", percent(evaluation.average_redundant_action_rate), "相邻重复动作占比，越低越好"],
        ["Exec Errors", evaluation.total_exec_errors || 0, `${{evaluation.exec_error_runs || 0}} 条运行出现执行错误`],
      ];
      $("#qualityMetrics").innerHTML = metrics.map(([label, value, hint]) => `
        <article class="quality-card">
          <label>${{escapeHtml(label)}}</label>
          <b>${{escapeHtml(value)}}</b>
          <small>${{escapeHtml(hint)}}</small>
        </article>
      `).join("");
    }}

    function renderScoreboard() {{
      const total = Number(evaluation.total_runs || 0);
      const completed = Number(evaluation.completed_runs || 0);
      const failed = Number(evaluation.failed_runs || 0);
      const artifactCompleteRuns = Number(evaluation.artifact_complete_runs || 0);
      const coverage = evaluation.coverage || {{}};
      const riskLabel = failed === 0
        ? "批次无失败"
        : `${{failed}} 条运行需要复核`;
      $("#scoreboard").innerHTML = `
        <article class="score-card">
          <label>批次健康度</label>
          <strong>${{percent(evaluation.success_rate)}}</strong>
          <p>${{escapeHtml(riskLabel)}}。已通过 ${{completed}} / ${{total}} 条运行。</p>
          <div class="health-band" style="--completed: ${{Math.max(completed, 0)}}fr; --failed: ${{Math.max(failed, 0)}}fr">
            <i></i><i></i>
          </div>
        </article>
        <article class="score-card">
          <label>证据完整度</label>
          <strong>${{percent(evaluation.artifact_complete_rate)}}</strong>
          <p>${{artifactCompleteRuns}} / ${{total}} 条运行具备报告、动作日志和截图证据。</p>
        </article>
        <article class="score-card">
          <label>覆盖面</label>
          <strong>${{coverage.products || 0}}</strong>
          <p>当前批次覆盖 ${{coverage.products || 0}} 个产品域、${{coverage.tasks || 0}} 类任务。</p>
        </article>
      `;
    }}

    function renderProductCards() {{
      const entries = Object.entries(evaluation.by_product || {{}});
      if (!entries.length) {{
        $("#productCards").innerHTML = '<div class="empty">暂无产品数据。</div>';
        return;
      }}
      $("#productCards").innerHTML = entries.map(([product, item]) => `
        <div class="product-row">
          <strong>${{escapeHtml(product)}}</strong>
          <div class="bar" aria-label="${{escapeHtml(product)}} 通过率">
            <i style="--value: ${{percent(item.success_rate)}}"></i>
          </div>
          <span>${{escapeHtml(percent(item.success_rate))}}</span>
        </div>
      `).join("");
    }}

    function renderGroupedRates(containerId, grouped, className, emptyText) {{
      const entries = Object.entries(grouped || {{}});
      if (!entries.length) {{
        $(containerId).innerHTML = `<div class="empty">${{escapeHtml(emptyText)}}</div>`;
        return;
      }}
      $(containerId).innerHTML = entries.map(([group, item]) => `
        <div class="${{className}}">
          <strong>${{escapeHtml(group)}}</strong>
          <div class="bar" aria-label="${{escapeHtml(group)}} 通过率">
            <i style="--value: ${{percent(item.success_rate)}}"></i>
          </div>
          <span>${{escapeHtml(percent(item.success_rate))}}</span>
        </div>
      `).join("");
    }}

    function renderActionMix() {{
      const entries = Object.entries(evaluation.action_type_totals || {{}});
      if (!entries.length) {{
        $("#actionMix").innerHTML = '<div class="empty">暂无动作统计。</div>';
        return;
      }}
      const max = Math.max(...entries.map(([, count]) => Number(count || 0)), 1);
      $("#actionMix").innerHTML = entries.map(([action, count]) => `
        <div class="action-row">
          <strong>${{escapeHtml(action)}}</strong>
          <div class="bar" aria-label="${{escapeHtml(action)}} 动作数量">
            <i style="--value: ${{Math.round((Number(count || 0) / max) * 100)}}%"></i>
          </div>
          <span>${{escapeHtml(count)}}</span>
        </div>
      `).join("");
    }}

    function renderLocatorMix() {{
      const entries = Object.entries(evaluation.locator_strategy_totals || {{}});
      if (!entries.length) {{
        $("#locatorMix").innerHTML = '<div class="empty">暂无 locator 统计。</div>';
        return;
      }}
      const max = Math.max(...entries.map(([, count]) => Number(count || 0)), 1);
      $("#locatorMix").innerHTML = entries.map(([strategy, count]) => `
        <div class="locator-row">
          <strong>${{escapeHtml(strategy)}}</strong>
          <div class="bar" aria-label="${{escapeHtml(strategy)}} 定位次数">
            <i style="--value: ${{Math.round((Number(count || 0) / max) * 100)}}%"></i>
          </div>
          <span>${{escapeHtml(count)}}</span>
        </div>
      `).join("");
    }}

    function renderCompletionMix() {{
      const entries = Object.entries(evaluation.completion_signal_counts || {{}});
      if (!entries.length) {{
        $("#completionMix").innerHTML = '<div class="empty">暂无完成信号统计。</div>';
        return;
      }}
      const max = Math.max(...entries.map(([, count]) => Number(count || 0)), 1);
      $("#completionMix").innerHTML = entries.map(([signal, count]) => `
        <div class="completion-row">
          <strong>${{escapeHtml(signal)}}</strong>
          <div class="bar" aria-label="${{escapeHtml(signal)}} 完成信号数量">
            <i style="--value: ${{Math.round((Number(count || 0) / max) * 100)}}%"></i>
          </div>
          <span>${{escapeHtml(count)}}</span>
        </div>
      `).join("");
    }}

    function renderFailureMix() {{
      const entries = Object.entries(evaluation.by_failure_type || {{}});
      if (!entries.length) {{
        $("#failureMix").innerHTML = '<div class="empty">暂无失败运行。</div>';
        return;
      }}
      const max = Math.max(...entries.map(([, count]) => Number(count || 0)), 1);
      $("#failureMix").innerHTML = entries.map(([type, count]) => `
        <div class="failure-row">
          <strong>${{escapeHtml(type)}}</strong>
          <div class="bar" aria-label="${{escapeHtml(type)}} 失败数量">
            <i style="--value: ${{Math.round((Number(count || 0) / max) * 100)}}%"></i>
          </div>
          <span>${{escapeHtml(count)}}</span>
        </div>
      `).join("");
    }}

    function renderTaskMix() {{
      const entries = Object.entries(evaluation.by_task || {{}});
      if (!entries.length) {{
        $("#taskMix").innerHTML = '<div class="empty">暂无任务数据。</div>';
        return;
      }}
      const max = Math.max(...entries.map(([, item]) => Number(item.runs || 0)), 1);
      $("#taskMix").innerHTML = entries.slice(0, 8).map(([task, item]) => `
        <div class="task-row">
          <strong class="compact-label" title="${{escapeHtml(task)}}">${{escapeHtml(compactTaskLabel(task))}}</strong>
          <div class="bar" aria-label="${{escapeHtml(task)}} 运行数量">
            <i style="--value: ${{Math.round((Number(item.runs || 0) / max) * 100)}}%"></i>
          </div>
          <span>${{escapeHtml(item.runs || 0)}}</span>
        </div>
      `).join("");
    }}

    function filteredRuns() {{
      const product = productFilter.value;
      const status = statusFilter.value;
      const failure = failureFilter.value;
      const query = searchFilter.value.trim().toLowerCase();
      return (evaluation.runs || []).filter((run) => {{
        const runFailure = run.failure_type || "__none__";
        const haystack = `${{run.run_id || ""}} ${{run.task_id || ""}}`.toLowerCase();
        return (product === "all" || run.product === product) &&
          (status === "all" || run.result === status) &&
          (failure === "all" || runFailure === failure) &&
          (!query || haystack.includes(query));
      }});
    }}

    function renderRuns() {{
      const runs = filteredRuns();
      $("#runCount").textContent = `${{runs.length}} 条可见`;
      if (!runs.length) {{
        $("#runsTable").innerHTML = `
          <tr><td colspan="10"><div class="empty">没有运行记录匹配当前筛选。</div></td></tr>
        `;
        return;
      }}
      $("#runsTable").innerHTML = runs.map((run) => {{
      const result = run.result || "not_recorded";
        const statusClass = result === "passed" ? "completed" : "failed";
        const runLabel = `<span class="run-id" title="${{escapeHtml(run.run_id)}}">${{escapeHtml(compactRunId(run.run_id))}}</span>`;
        const resultLabel = result === "passed" ? "通过" : result === "failed" ? "失败" : result === "not_recorded" ? "未记录" : result;
        return `
          <tr data-run-row="${{escapeHtml(run.run_id)}}" tabindex="0" aria-label="选择运行 ${{escapeHtml(run.run_id)}}">
            <td>${{runLabel}}</td>
            <td><span class="compact-label" title="${{escapeHtml(run.task_id || "-")}}">${{escapeHtml(compactTaskLabel(run.task_id))}}</span></td>
            <td>${{escapeHtml(run.product || "general")}}</td>
            <td><span class="pill ${{statusClass}}">${{escapeHtml(resultLabel)}}</span></td>
            <td>${{escapeHtml(run.failure_type || "-")}}</td>
            <td>${{escapeHtml(duration(run.duration_sec))}}</td>
            <td>${{escapeHtml(run.observed_steps ?? "-")}}</td>
            <td>${{escapeHtml(percent(run.assertion_pass_rate))}}</td>
            <td>${{escapeHtml(run.screenshot_count ?? 0)}}</td>
            <td>
              <div class="table-actions">
                <button class="row-button" data-run-id="${{escapeHtml(run.run_id)}}">明细</button>
                <a class="row-button" href="${{escapeHtml(runPath(run, "report"))}}">报告</a>
              </div>
            </td>
          </tr>
        `;
      }}).join("");
      document.querySelectorAll("[data-run-row]").forEach((row) => {{
        row.addEventListener("click", () => renderRunDetail(row.dataset.runRow));
        row.addEventListener("keydown", (event) => {{
          if (event.key === "Enter" || event.key === " ") {{
            event.preventDefault();
            renderRunDetail(row.dataset.runRow);
          }}
        }});
      }});
      document.querySelectorAll("[data-run-id]").forEach((button) => {{
        button.addEventListener("click", (event) => {{
          event.stopPropagation();
          renderRunDetail(button.dataset.runId);
        }});
      }});
      if (!$("#runDetail").dataset.selected && runs[0]) {{
        renderRunDetail(runs[0].run_id);
      }}
    }}

    function renderRunDetail(runId) {{
      const run = (evaluation.runs || []).find((item) => item.run_id === runId);
      const detail = $("#runDetail");
      if (!run) {{
        detail.innerHTML = '<h3>运行明细</h3><p class="empty">未找到运行记录。</p>';
        return;
      }}
      detail.dataset.selected = runId || "";
      document.querySelectorAll("[data-run-row]").forEach((row) => {{
        row.classList.toggle("selected", row.dataset.runRow === runId);
      }});
      const status = run.result || "not_recorded";
      const statusClass = status === "passed" ? "completed" : "failed";
      const statusLabel = status === "passed" ? "通过" : status === "failed" ? "失败" : status === "not_recorded" ? "未记录" : status;
      const locator = run.locator_stats || {{}};
      const execErrors = Array.isArray(run.exec_errors) ? run.exec_errors : [];
      const execErrorText = execErrors.length
        ? execErrors.map((item) => `${{item.step_id || "-"}}:${{item.failure_reason || item.status || "error"}}`).join("；")
        : "-";
      detail.innerHTML = `
        <h3>${{escapeHtml(run.run_id || "ad_hoc_run")}}</h3>
        <span class="pill ${{statusClass}}">${{escapeHtml(statusLabel)}}</span>
        <div class="detail-actions" style="margin: 14px 0 4px;">
          <a class="detail-link" href="${{escapeHtml(runPath(run, "report"))}}">打开报告</a>
          <a class="detail-link" href="${{escapeHtml(runPath(run, "summary"))}}">Summary JSON</a>
          <a class="detail-link" href="${{escapeHtml(runPath(run, "replay"))}}">回放草稿</a>
        </div>
        <div class="detail-line"><span>任务</span><b>${{escapeHtml(run.task_id || "-")}}</b></div>
        <div class="detail-line"><span>产品</span><b>${{escapeHtml(run.product || "general")}}</b></div>
        <div class="detail-line"><span>优先级 / 复杂度</span><b>${{escapeHtml(run.priority || "medium")}} / ${{escapeHtml(run.complexity || "medium")}}</b></div>
        <div class="detail-line"><span>失败类型</span><b>${{escapeHtml(run.failure_type || "无")}}</b></div>
        <div class="detail-line"><span>耗时</span><b>${{escapeHtml(duration(run.duration_sec))}}</b></div>
        <div class="detail-line"><span>观测步数</span><b>${{escapeHtml(run.observed_steps ?? "-")}}</b></div>
        <div class="detail-line"><span>Step Efficiency</span><b>${{escapeHtml(percent(run.step_efficiency))}}</b></div>
        <div class="detail-line"><span>Partial Credit</span><b>${{escapeHtml(percent(run.partial_credit))}}</b></div>
        <div class="detail-line"><span>断言通过</span><b>${{escapeHtml(percent(run.assertion_pass_rate))}}</b></div>
        <div class="detail-line"><span>Reflection Count</span><b>${{escapeHtml(run.reflection_count ?? "-")}}</b></div>
        <div class="detail-line"><span>Redundant Action</span><b>${{escapeHtml(percent(run.redundant_action_rate))}}</b></div>
        <div class="detail-line"><span>Locator Match</span><b>${{escapeHtml(percent(locator.match_rate))}}（${{escapeHtml(locator.matched ?? 0)}} / ${{escapeHtml(locator.total ?? 0)}}）</b></div>
        <div class="detail-line"><span>Completion Signal</span><b>${{escapeHtml(run.completion_signal || "-")}}</b></div>
        <div class="detail-line"><span>Exec Errors</span><b>${{escapeHtml(run.exec_error_count ?? 0)}}：${{escapeHtml(execErrorText)}}</b></div>
        <div class="detail-line"><span>截图数</span><b>${{escapeHtml(run.screenshot_count ?? 0)}}</b></div>
        <div class="detail-line"><span>证据完整</span><b>${{escapeHtml(run.artifact_complete ? "是" : "否")}}</b></div>
        <div class="detail-line"><span>失败原因</span><b>${{escapeHtml(run.failure_reason || "-")}}</b></div>
        <div class="detail-line"><span>报告路径</span><b>${{escapeHtml(run.report_path || "-")}}</b></div>
        <div class="detail-line"><span>最终截图</span><b>${{escapeHtml(run.final_screenshot || "-")}}</b></div>
        <div class="detail-line"><span>Summary 路径</span><b>${{escapeHtml(run.summary_path || "-")}}</b></div>
      `;
    }}

    function restoreSelectValue(node, value) {{
      if (!node) {{
        return;
      }}
      const options = Array.from(node.options || []);
      if (options.some((item) => item.value === value)) {{
        node.value = value;
      }}
    }}

    function replaceEvaluation(nextEvaluation) {{
      const selectedRunId = $("#runDetail").dataset.selected || "";
      const filterState = {{
        product: productFilter.value,
        status: statusFilter.value,
        failure: failureFilter.value,
        search: searchFilter.value,
      }};
      evaluation = nextEvaluation;
      dashboardSnapshotId = nextEvaluation.dashboard_snapshot_id || dashboardSnapshotId;
      initGeneratedAt();
      initFilters();
      restoreSelectValue(productFilter, filterState.product);
      restoreSelectValue(statusFilter, filterState.status);
      restoreSelectValue(failureFilter, filterState.failure);
      searchFilter.value = filterState.search;
      $("#runDetail").dataset.selected = "";
      renderAll();
      if (
        selectedRunId &&
        (evaluation.runs || []).some((item) => item.run_id === selectedRunId)
      ) {{
        renderRunDetail(selectedRunId);
      }}
    }}

    async function pollDashboardData() {{
      if (!window.fetch) {{
        setRefreshStatus("Auto refresh: unsupported");
        return;
      }}
      try {{
        const response = await fetch(DASHBOARD_API_URL, {{
          cache: "no-store",
          headers: {{ Accept: "application/json" }},
        }});
        if (!response.ok) {{
          setRefreshStatus(`Auto refresh: HTTP ${{response.status}}`);
          return;
        }}
        const nextEvaluation = await response.json();
        const nextSnapshotId = nextEvaluation.dashboard_snapshot_id || null;
        if (!dashboardSnapshotId && nextSnapshotId) {{
          dashboardSnapshotId = nextSnapshotId;
        }}
        if (
          nextSnapshotId &&
          dashboardSnapshotId &&
          nextSnapshotId !== dashboardSnapshotId
        ) {{
          replaceEvaluation(nextEvaluation);
          setRefreshStatus(
            `Auto refresh: synced · pending ${{nextEvaluation.pending_run_count || 0}}`
          );
          return;
        }}
        setRefreshStatus(
          `Auto refresh: watching · pending ${{nextEvaluation.pending_run_count || 0}}`
        );
      }} catch (_error) {{
        setRefreshStatus("Auto refresh: offline");
      }}
    }}

    function startDashboardPolling() {{
      setRefreshStatus("Auto refresh: 5s polling");
      pollDashboardData();
      dashboardRefreshTimer = window.setInterval(pollDashboardData, DASHBOARD_POLL_MS);
      window.addEventListener(
        "beforeunload",
        () => {{
          if (dashboardRefreshTimer !== null) {{
            window.clearInterval(dashboardRefreshTimer);
            dashboardRefreshTimer = null;
          }}
        }},
        {{ once: true }}
      );
    }}

    function renderAll() {{
      renderMetrics();
      renderQualityMetrics();
      renderScoreboard();
      renderPendingPanel();
      renderProductCards();
      renderGroupedRates("#priorityMix", evaluation.by_priority, "group-row", "暂无优先级数据。");
      renderGroupedRates("#complexityMix", evaluation.by_complexity, "group-row", "暂无复杂度数据。");
      renderActionMix();
      renderLocatorMix();
      renderCompletionMix();
      renderFailureMix();
      renderTaskMix();
      renderRuns();
    }}

    [productFilter, statusFilter, failureFilter, searchFilter]
      .forEach((node) => node.addEventListener("input", renderRuns));

    initGeneratedAt();
    initFilters();
    renderAll();
    startDashboardPolling();
  </script>
</body>
</html>
"""


def _summary_path(summary: dict[str, Any]) -> Path | None:
    value = summary.get("_summary_path")
    if not value:
        return None
    return Path(str(value))


def _artifact_exists(path: Path | None) -> bool:
    return bool(path and path.exists() and path.is_file())


def _nonempty_artifact(path: Path | None) -> bool:
    return bool(_artifact_exists(path) and path.stat().st_size > 0)


def _run_artifacts(summary: dict[str, Any]) -> dict[str, Any]:
    summary_path = _summary_path(summary)
    run_dir = summary_path.parent if summary_path else None
    report_path = run_dir / "report.md" if run_dir else None
    actions_path = run_dir / "actions.jsonl" if run_dir else None
    semantic_trace_path = run_dir / "semantic_trace.json" if run_dir else None
    replay_draft_path = run_dir / "replay_draft.md" if run_dir else None
    screenshot_dir = run_dir / "screenshots" if run_dir else None
    screenshot_count = 0
    if screenshot_dir and screenshot_dir.exists() and screenshot_dir.is_dir():
        screenshot_count = sum(1 for item in screenshot_dir.iterdir() if item.is_file())
    screenshot_refs = summary.get("screenshots", [])
    if isinstance(screenshot_refs, list):
        screenshot_count = max(screenshot_count, len(screenshot_refs))

    return {
        "run_dir": str(run_dir) if run_dir else None,
        "summary": str(summary_path) if summary_path else None,
        "report": str(report_path) if _artifact_exists(report_path) else None,
        "actions": str(actions_path) if _nonempty_artifact(actions_path) else None,
        "screenshots_count": screenshot_count,
        "semantic_trace": (
            str(semantic_trace_path) if _artifact_exists(semantic_trace_path) else None
        ),
        "replay_draft": (
            str(replay_draft_path) if _artifact_exists(replay_draft_path) else None
        ),
    }


def _assertions_passed(summary: dict[str, Any]) -> tuple[bool, bool]:
    assertions = summary.get("assertions", [])
    if not isinstance(assertions, list) or not assertions:
        return False, False
    for assertion in assertions:
        if not isinstance(assertion, dict) or not assertion.get("passed"):
            return True, False
    return True, True


def _live_e2e_run(summary: dict[str, Any]) -> dict[str, Any]:
    artifacts = _run_artifacts(summary)
    has_assertions, assertions_passed = _assertions_passed(summary)
    checks = {
        "agent_s3_feishu": summary.get("intent") == "agent_s3_feishu",
        "status_completed": _success(summary),
        "has_summary_json": bool(artifacts["summary"]),
        "has_report_md": bool(artifacts["report"]),
        "has_actions_jsonl": bool(artifacts["actions"]),
        "has_screenshots": artifacts["screenshots_count"] > 0,
        "has_assertions": has_assertions,
        "assertions_passed": assertions_passed,
    }
    artifact_complete = all(
        checks[key]
        for key in (
            "has_summary_json",
            "has_report_md",
            "has_actions_jsonl",
            "has_screenshots",
        )
    )
    live_e2e_passed = artifact_complete and all(
        checks[key]
        for key in (
            "agent_s3_feishu",
            "status_completed",
            "has_assertions",
            "assertions_passed",
        )
    )
    missing = [key for key, passed in checks.items() if not passed]
    return {
        "run_id": summary.get("run_id"),
        "task_id": summary.get("task_id"),
        "product": _field_label(summary, "product"),
        "status": summary.get("status"),
        "evidence_level": "live_e2e" if live_e2e_passed else "runtime_artifact",
        "artifact_complete": artifact_complete,
        "live_e2e_passed": live_e2e_passed,
        "checks": checks,
        "missing": missing,
        "artifacts": artifacts,
    }


def _live_e2e_by_product(
    runs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(_label(run.get("product"), "general"), []).append(run)

    by_product: dict[str, dict[str, Any]] = {}
    for product, items in sorted(grouped.items()):
        artifact_complete = sum(1 for item in items if item["artifact_complete"])
        live_passed = sum(1 for item in items if item["live_e2e_passed"])
        by_product[product] = {
            "runs": len(items),
            "artifact_complete": artifact_complete,
            "live_e2e_passed": live_passed,
            "live_e2e_rate": _percent(live_passed, len(items)),
        }
    return by_product


def build_live_e2e_evidence(
    summaries: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a Live E2E evidence pack from per-run artifacts."""

    runs = [_live_e2e_run(summary) for summary in summaries]
    artifact_complete = sum(1 for run in runs if run["artifact_complete"])
    live_passed = sum(1 for run in runs if run["live_e2e_passed"])
    return {
        "generated_at": generated_at or _now_iso(),
        "total_runs": len(runs),
        "artifact_complete_runs": artifact_complete,
        "live_e2e_passed_runs": live_passed,
        "live_e2e_rate": _percent(live_passed, len(runs)),
        "by_product": _live_e2e_by_product(runs),
        "runs": runs,
    }


def build_live_e2e_markdown(evidence: dict[str, Any]) -> str:
    """Build a human-readable Live E2E evidence report."""

    lines = [
        "# Feishu Live E2E Evidence",
        "",
        "## Summary",
        f"- Generated At: `{evidence.get('generated_at')}`",
        f"- Total Runs: `{evidence.get('total_runs')}`",
        f"- Artifact Complete Runs: `{evidence.get('artifact_complete_runs')}`",
        f"- Live E2E Passed Runs: `{evidence.get('live_e2e_passed_runs')}`",
        f"- Live E2E Rate: `{evidence.get('live_e2e_rate')}`",
        "",
        "## By Product",
    ]

    for product, item in evidence.get("by_product", {}).items():
        lines.append(
            f"- `{product}`: runs `{item['runs']}`, "
            f"artifact_complete `{item['artifact_complete']}`, "
            f"live_e2e_passed `{item['live_e2e_passed']}`, "
            f"live_e2e_rate `{item['live_e2e_rate']}`"
        )

    lines.extend(["", "## Runs"])
    for run in evidence.get("runs", []):
        status = "passed" if run.get("live_e2e_passed") else "incomplete"
        missing = run.get("missing") or []
        missing_text = ", ".join(missing) if missing else "none"
        artifacts = run.get("artifacts", {})
        lines.append(
            f"- `{run.get('run_id')}` `{run.get('product')}` "
            f"`{run.get('task_id')}` => `{status}`"
        )
        lines.append(f"  missing: `{missing_text}`")
        lines.append(
            "  artifacts: "
            f"summary `{artifacts.get('summary')}`, "
            f"report `{artifacts.get('report')}`, "
            f"actions `{artifacts.get('actions')}`, "
            f"screenshots `{artifacts.get('screenshots_count')}`"
        )
    return "\n".join(lines) + "\n"


def write_evaluation_report(
    artifact_root: str | Path,
    output_dir: str | Path,
) -> dict[str, str]:
    """Aggregate run summaries and write evaluation artifacts."""

    summaries = discover_run_summaries(artifact_root)
    evaluation = build_evaluation_summary(summaries)
    live_e2e = build_live_e2e_evidence(summaries)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    summary_path = output_path / "evaluation_summary.json"
    report_path = output_path / "evaluation_report.md"
    dashboard_path = output_path / "evaluation_dashboard.html"
    live_e2e_json_path = output_path / "live_e2e_evidence.json"
    live_e2e_md_path = output_path / "live_e2e_evidence.md"
    summary_path.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(build_evaluation_markdown(evaluation), encoding="utf-8")
    dashboard_path.write_text(
        build_evaluation_dashboard_html(evaluation),
        encoding="utf-8",
    )
    live_e2e_json_path.write_text(
        json.dumps(live_e2e, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    live_e2e_md_path.write_text(
        build_live_e2e_markdown(live_e2e),
        encoding="utf-8",
    )
    return {
        "evaluation_summary": str(summary_path),
        "evaluation_report": str(report_path),
        "evaluation_dashboard": str(dashboard_path),
        "live_e2e_evidence": str(live_e2e_json_path),
        "live_e2e_report": str(live_e2e_md_path),
    }
