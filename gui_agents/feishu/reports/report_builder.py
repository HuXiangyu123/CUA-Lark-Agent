"""Build structured and human-readable run reports."""

from __future__ import annotations

from collections import Counter
import datetime as dt
from pathlib import Path
import re
from typing import Any

from gui_agents.feishu.maintenance.artifact_manager import ArtifactManager

_FORBIDDEN_SEMANTIC_TOKENS = (
    "relative_bounds",
    "bbox",
    "bounding_box",
    "coordinate",
    "coordinates",
    "confidence",
    "pixel",
    "pixels",
    "resolution",
    "image_width",
    "image_height",
)

_ALLOWED_SEMANTIC_STEP_FIELDS = {
    "step_index",
    "step_id",
    "product",
    "page_type",
    "visible_controls",
    "anomalies",
    "recovery_hint",
    "action_summary",
    "verification",
    "verification_passed",
    "failure_type",
    "recovery_attempt",
    "timestamp",
}

_SUCCESS_STATUSES = {"completed", "passed"}
_EMPTY_LABELS = {"", "unknown", "none", "null", "n/a", "-"}


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def _contains_forbidden_semantic_token(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in _FORBIDDEN_SEMANTIC_TOKENS)


def _is_forbidden_semantic_key(value: str) -> bool:
    lowered = value.lower()
    if lowered in {"x", "y"}:
        return True
    return any(token in lowered for token in _FORBIDDEN_SEMANTIC_TOKENS)


def _safe_semantic_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or _contains_forbidden_semantic_token(text):
        return None
    if re.search(r"\(\s*\d+\s*,\s*\d+", text):
        return None
    return text


def _semantic_default(value: Any, default: str) -> str:
    text = _safe_semantic_text(value)
    if text is None or text.strip().lower() in _EMPTY_LABELS:
        return default
    return text


def _safe_semantic_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _safe_semantic_text(item)
        if text:
            items.append(text)
    return items


def _ratio_or_none(numerator: int | float, denominator: int | float) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _format_percent(value: Any) -> str:
    if not isinstance(value, int | float):
        return "-"
    return f"{float(value) * 100:.1f}%"


def _count_actions(action_logs: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for action_log in action_logs:
        action = _semantic_default(action_log.get("action"), "exec")
        counts[action] += 1
    return dict(sorted(counts.items()))


def _count_anomaly_types(anomaly_events: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for event in anomaly_events:
        anomaly_type = _safe_semantic_text(event.get("anomaly_type"))
        if anomaly_type:
            counts[anomaly_type] += 1
    return dict(sorted(counts.items()))


def _completion_signal(runtime_context: dict[str, Any]) -> str:
    action_logs = runtime_context.get("action_logs", [])
    if action_logs:
        last_action = str(action_logs[-1].get("action") or "").strip()
        if last_action:
            return last_action
    status = _semantic_default(runtime_context.get("status"), "not_recorded")
    if status == "not_recorded":
        return status
    return f"status_{status}"


def _partial_credit(*values: Any) -> float | None:
    numerics = [
        float(value)
        for value in values
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]
    if not numerics:
        return None
    return round(sum(numerics) / len(numerics), 4)


def _reflection_count(runtime_context: dict[str, Any]) -> int:
    seen: set[str] = set()
    reflections = runtime_context.get("reflections")
    if isinstance(reflections, list):
        for item in reflections:
            text = _safe_semantic_text(item)
            if text:
                seen.add(text)

    for item in runtime_context.get("action_logs", []):
        if isinstance(item, dict):
            text = _safe_semantic_text(item.get("reflection"))
            if text:
                seen.add(text)
    for item in runtime_context.get("step_results", []):
        if isinstance(item, dict):
            text = _safe_semantic_text(item.get("reflection"))
            if text:
                seen.add(text)
    return len(seen)


def _action_signature(action_log: dict[str, Any]) -> tuple[str, str, str]:
    action = _semantic_default(action_log.get("action"), "exec")
    target = str(action_log.get("target") or "")
    params = action_log.get("params", {})
    param_hint = ""
    if isinstance(params, dict):
        for key in ("text", "target", "label", "code"):
            value = params.get(key)
            if value:
                param_hint = str(value).strip()[:160]
                break
    return action, target, param_hint


def _redundant_action_rate(action_logs: list[dict[str, Any]]) -> float | None:
    if not action_logs:
        return 0.0
    redundant = 0
    previous: tuple[str, str, str] | None = None
    for action_log in action_logs:
        signature = _action_signature(action_log)
        if previous is not None and signature == previous:
            redundant += 1
        previous = signature
    return round(redundant / len(action_logs), 4)


def _locator_stats(step_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    matched = 0
    failed = 0
    strategy_counts = Counter()
    for step_result in step_results:
        locator_result = step_result.get("locator_result")
        if not isinstance(locator_result, dict):
            continue
        if "matched" not in locator_result and "strategy" not in locator_result:
            continue
        total += 1
        if locator_result.get("matched") is True:
            matched += 1
        elif locator_result.get("matched") is False:
            failed += 1
        strategy = _semantic_default(locator_result.get("strategy"), "not_recorded")
        strategy_counts[strategy] += 1
    return {
        "total": total,
        "matched": matched,
        "failed": failed,
        "match_rate": _ratio_or_none(matched, total),
        "strategy_counts": dict(sorted(strategy_counts.items())),
    }


def _exec_errors(
    action_logs: list[dict[str, Any]],
    step_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for action_log in action_logs:
        status = str(action_log.get("status") or "").lower()
        if status not in {"failed", "error"}:
            continue
        item = {
            "step_id": action_log.get("step_id"),
            "action": action_log.get("action"),
            "status": action_log.get("status"),
            "failure_reason": action_log.get("failure_reason"),
        }
        key = (item["step_id"], item["action"], item["failure_reason"])
        if key not in seen:
            errors.append(item)
            seen.add(key)

    for step_result in step_results:
        if step_result.get("failure_type") != "runtime":
            continue
        item = {
            "step_id": step_result.get("step_id"),
            "action": step_result.get("action"),
            "status": step_result.get("status"),
            "failure_reason": step_result.get("failure_reason"),
        }
        key = (item["step_id"], item["action"], item["failure_reason"])
        if key not in seen:
            errors.append(item)
            seen.add(key)
    return errors


def _result_label(status: Any) -> str:
    normalized = str(status or "not_recorded").strip().lower()
    if normalized in _EMPTY_LABELS:
        return "not_recorded"
    if normalized in _SUCCESS_STATUSES:
        return "passed"
    if normalized in {"failed", "error"}:
        return "failed"
    return normalized or "not_recorded"


def _default_complexity(
    explicit: Any,
    *,
    planned_steps: int,
    observed_steps: int,
    action_logs: list[dict[str, Any]],
    task_id: Any,
) -> str:
    explicit_text = _safe_semantic_text(explicit)
    if explicit_text and explicit_text.strip().lower() not in _EMPTY_LABELS:
        return explicit_text

    task_text = str(task_id or "").lower()
    if any(token in task_text for token in ("cross_window", "share", "invite")):
        return "high"

    size = max(planned_steps, observed_steps, len(action_logs))
    if size <= 2:
        return "low"
    if size <= 6:
        return "medium"
    return "high"


def _step_artifacts(
    step_results: list[dict[str, Any]],
    screenshots: list[Any],
) -> list[dict[str, Any]]:
    screenshot_paths = [str(item) for item in screenshots if item]
    artifacts: list[dict[str, Any]] = []
    for index, step_result in enumerate(step_results, start=1):
        verification = step_result.get("verification_result", {})
        assertion = verification.get("assertion")
        assertion_passed = verification.get("passed")
        artifacts.append(
            {
                "index": index,
                "step_id": step_result.get("step_id"),
                "stage": step_result.get("stage"),
                "action": step_result.get("action"),
                "status": step_result.get("status"),
                "result": (
                    "passed" if step_result.get("status") == "passed" else "failed"
                ),
                "assertion": assertion,
                "assertion_passed": (
                    bool(assertion_passed) if assertion is not None else None
                ),
                "failure_type": step_result.get("failure_type"),
                "failure_reason": step_result.get("failure_reason"),
                "screenshot": (
                    screenshot_paths[index - 1]
                    if index - 1 < len(screenshot_paths)
                    else None
                ),
            }
        )
    return artifacts


def _markdown_link(path: str | None) -> str:
    if not path:
        return "-"
    name = Path(path).name
    return f"[{name}]({path})"


def _clean_anomaly_events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    events: list[dict[str, Any]] = []
    for raw_event in value:
        if not isinstance(raw_event, dict):
            continue
        anomaly_type = _safe_semantic_text(raw_event.get("anomaly_type"))
        if not anomaly_type:
            continue

        event: dict[str, Any] = {"anomaly_type": anomaly_type}
        step_index = raw_event.get("step_index")
        if isinstance(step_index, int):
            event["step_index"] = step_index
        for field in ("product", "page_type", "recovery_hint", "timestamp"):
            text = _safe_semantic_text(raw_event.get(field))
            if text is not None:
                event[field] = text
        events.append(event)
    return events


def _events_by_step(
    anomaly_events: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for event in anomaly_events:
        step_index = event.get("step_index")
        if isinstance(step_index, int):
            grouped.setdefault(step_index, []).append(event)
    return grouped


def _anomaly_names(events: list[dict[str, Any]]) -> list[str]:
    names = [
        text
        for text in (_safe_semantic_text(event.get("anomaly_type")) for event in events)
        if text
    ]
    return sorted(dict.fromkeys(names))


def _first_recovery_hint(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        hint = _safe_semantic_text(event.get("recovery_hint"))
        if hint:
            return hint
    return None


class ReportBuilder:
    """Build Track D artifacts from testcase and runtime outputs."""

    def __init__(self, artifact_manager: ArtifactManager | None = None) -> None:
        self.artifact_manager = artifact_manager or ArtifactManager()

    def _completed_at(self, runtime_context: dict[str, Any]) -> dt.datetime:
        action_logs = runtime_context.get("action_logs", [])
        if action_logs:
            parsed = _parse_iso(action_logs[-1].get("timestamp"))
            if parsed is not None:
                return parsed
        return dt.datetime.now(dt.timezone.utc).astimezone()

    def _assertion_results(
        self,
        testcase: dict[str, Any] | None,
        runtime_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if testcase is not None:
            assertions = testcase.get("assertions", [])
        else:
            assertions = [
                item.get("assertion")
                for item in runtime_context.get("assertion_plan", [])
                if item.get("assertion")
            ]
        step_results = runtime_context.get("step_results", [])
        seen: dict[str, dict[str, Any]] = {}
        for step_result in step_results:
            verification = step_result.get("verification_result", {})
            assertion = verification.get("assertion")
            if not assertion or assertion in seen:
                continue
            seen[assertion] = {
                "name": assertion,
                "passed": bool(verification.get("passed")),
                "failure_reason": verification.get("failure_reason"),
            }
        return [
            seen.get(
                assertion,
                {
                    "name": assertion,
                    "passed": False,
                    "failure_reason": "assertion not observed in runtime results",
                },
            )
            for assertion in assertions
        ]

    def build_summary(
        self,
        testcase: dict[str, Any] | None,
        runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        started_at = _parse_iso(runtime_context.get("started_at"))
        completed_at = self._completed_at(runtime_context)
        duration_sec = 0.0
        if started_at is not None:
            duration_sec = max((completed_at - started_at).total_seconds(), 0.0)

        step_results = runtime_context.get("step_results", [])
        failed_steps = [step for step in step_results if step.get("status") != "passed"]
        passed_steps = len(step_results) - len(failed_steps)
        assertions = self._assertion_results(testcase, runtime_context)
        assertion_passed = sum(1 for item in assertions if item.get("passed"))
        screenshots = [
            str(item) for item in runtime_context.get("screenshots", []) if item
        ]
        action_logs = runtime_context.get("action_logs", [])
        action_type_counts = _count_actions(action_logs)
        anomaly_events = _clean_anomaly_events(runtime_context.get("anomaly_events"))
        planned_steps = len((testcase or {}).get("steps", [])) or len(step_results)
        metadata = (testcase or {}).get("metadata", {})
        estimated_steps = metadata.get("estimated_steps")
        if not isinstance(estimated_steps, int) or estimated_steps <= 0:
            estimated_steps = planned_steps
        observed_steps = len(step_results)
        step_pass_rate = _ratio_or_none(passed_steps, observed_steps)
        step_efficiency = _ratio_or_none(estimated_steps, observed_steps)
        if isinstance(step_efficiency, float):
            step_efficiency = round(min(step_efficiency, 1.0), 4)
        assertion_pass_rate = _ratio_or_none(assertion_passed, len(assertions))
        partial_credit = _partial_credit(step_pass_rate, assertion_pass_rate)
        exec_errors = _exec_errors(action_logs, step_results)
        locator_stats = _locator_stats(step_results)
        priority = (
            (testcase or {}).get("priority")
            or metadata.get("priority")
            or runtime_context.get("priority")
        )
        complexity = (
            (testcase or {}).get("complexity")
            or metadata.get("complexity")
            or runtime_context.get("complexity")
        )
        product = (testcase or {}).get("product") or runtime_context.get("product")
        task_id = (testcase or {}).get("id") or runtime_context.get("task_id")
        priority = _semantic_default(priority, "medium")
        complexity = _default_complexity(
            complexity,
            planned_steps=planned_steps,
            observed_steps=observed_steps,
            action_logs=action_logs,
            task_id=task_id,
        )

        return {
            "task_id": _semantic_default(task_id, "ad_hoc_task"),
            "product": _semantic_default(product, "general"),
            "priority": priority,
            "complexity": complexity,
            "intent": runtime_context.get("intent"),
            "params": runtime_context.get("params", {}),
            "status": runtime_context.get("status"),
            "result": _result_label(runtime_context.get("status")),
            "steps": planned_steps,
            "planned_steps": planned_steps,
            "estimated_steps": estimated_steps,
            "observed_steps": observed_steps,
            "passed_steps": passed_steps,
            "failed_steps": len(failed_steps),
            "step_pass_rate": step_pass_rate,
            "step_efficiency": step_efficiency,
            "partial_credit": partial_credit,
            "duration_sec": round(duration_sec, 3),
            "assertions": assertions,
            "assertion_total": len(assertions),
            "assertion_passed": assertion_passed,
            "assertion_failed": len(assertions) - assertion_passed,
            "assertion_pass_rate": assertion_pass_rate,
            "screenshots": screenshots,
            "screenshot_count": len(screenshots),
            "step_artifacts": _step_artifacts(step_results, screenshots),
            "action_type_counts": action_type_counts,
            "action_total": sum(action_type_counts.values()),
            "completion_signal": _completion_signal(runtime_context),
            "reflection_count": _reflection_count(runtime_context),
            "redundant_action_rate": _redundant_action_rate(action_logs),
            "locator_stats": locator_stats,
            "exec_error_count": len(exec_errors),
            "exec_errors": exec_errors,
            "recovery_attempts": int(runtime_context.get("recovery_attempts") or 0),
            "anomaly_events_count": len(anomaly_events),
            "anomaly_type_counts": _count_anomaly_types(anomaly_events),
            "anomaly_events": anomaly_events,
            "failure_type": runtime_context.get("failure_type"),
            "failure_reason": runtime_context.get("failure_reason"),
            "run_id": runtime_context.get("run_id"),
            "started_at": runtime_context.get("started_at"),
            "completed_at": completed_at.isoformat(),
        }

    def build_markdown(
        self,
        summary: dict[str, Any],
        runtime_context: dict[str, Any],
        testcase: dict[str, Any] | None = None,
    ) -> str:
        lines = [
            "# Feishu Run Report",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Run ID | `{summary.get('run_id')}` |",
            f"| Task ID | `{summary.get('task_id')}` |",
            f"| Product | `{summary.get('product')}` |",
            f"| Intent | `{summary.get('intent')}` |",
            f"| Status | `{summary.get('status')}` |",
            f"| Result | `{summary.get('result')}` |",
            f"| Duration (s) | `{summary.get('duration_sec')}` |",
            f"| Planned Steps | `{summary.get('planned_steps')}` |",
            f"| Observed Steps | `{summary.get('observed_steps')}` |",
            f"| Step Pass Rate | `{_format_percent(summary.get('step_pass_rate'))}` |",
            f"| Assertion Pass Rate | `{_format_percent(summary.get('assertion_pass_rate'))}` |",
            f"| Screenshot Count | `{summary.get('screenshot_count')}` |",
            f"| Step Efficiency | `{_format_percent(summary.get('step_efficiency'))}` |",
            f"| Partial Credit | `{_format_percent(summary.get('partial_credit'))}` |",
            f"| Redundant Action Rate | `{_format_percent(summary.get('redundant_action_rate'))}` |",
            f"| Reflection Count | `{summary.get('reflection_count')}` |",
            f"| Exec Errors | `{summary.get('exec_error_count')}` |",
            f"| Failure Type | `{summary.get('failure_type')}` |",
            f"| Failure Reason | `{summary.get('failure_reason')}` |",
            "",
            "## Assertions",
            "",
            "| Assertion | Result | Reason |",
            "|---|---|---|",
        ]
        for assertion in summary.get("assertions", []):
            lines.append(
                f"| `{assertion['name']}` | "
                f"{'passed' if assertion.get('passed') else 'failed'} | "
                f"{assertion.get('failure_reason') or '-'} |"
            )

        lines.extend(
            [
                "",
                "## Execution Trace",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Action Total | `{summary.get('action_total')}` |",
                f"| Action Type Counts | `{summary.get('action_type_counts')}` |",
                f"| Completion Signal | `{summary.get('completion_signal')}` |",
                f"| Locator Stats | `{summary.get('locator_stats')}` |",
                f"| Recovery Attempts | `{summary.get('recovery_attempts')}` |",
                f"| Anomaly Events | `{summary.get('anomaly_events_count')}` |",
                "",
                "## Steps",
                "",
                "| Step | Stage | Action | Status | Assertion | Screenshot |",
                "|---|---|---|---|---|---|",
            ]
        )
        for step_artifact in summary.get("step_artifacts", []):
            lines.append(
                f"| `{step_artifact.get('step_id')}` | "
                f"`{step_artifact.get('stage')}` | "
                f"`{step_artifact.get('action')}` | "
                f"`{step_artifact.get('status')}` | "
                f"`{step_artifact.get('assertion') or '-'}` | "
                f"{_markdown_link(step_artifact.get('screenshot'))} |"
            )

        lines.extend(["", "## Step Gallery"])
        for step_artifact in summary.get("step_artifacts", []):
            lines.extend(
                [
                    "",
                    f"### `{step_artifact.get('step_id')}`",
                    f"- Stage: `{step_artifact.get('stage')}`",
                    f"- Action: `{step_artifact.get('action')}`",
                    f"- Status: `{step_artifact.get('status')}`",
                    f"- Assertion: `{step_artifact.get('assertion') or '-'}`",
                    f"- Failure Type: `{step_artifact.get('failure_type')}`",
                    f"- Failure Reason: `{step_artifact.get('failure_reason')}`",
                    f"- Screenshot: {_markdown_link(step_artifact.get('screenshot'))}",
                ]
            )

        lines.extend(
            [
                "",
                "## Anomaly Events",
                "",
                "| Step | Product | Page | Type | Recovery Hint |",
                "|---:|---|---|---|---|",
            ]
        )
        anomaly_events = summary.get("anomaly_events", [])
        if anomaly_events:
            for event in anomaly_events:
                lines.append(
                    f"| `{event.get('step_index', '-')}` | "
                    f"`{event.get('product') or '-'}` | "
                    f"`{event.get('page_type') or '-'}` | "
                    f"`{event.get('anomaly_type')}` | "
                    f"`{event.get('recovery_hint') or '-'}` |"
                )
        else:
            lines.append("| - | - | - | - | - |")

        artifact_manifest = summary.get("artifact_manifest", {})
        lines.extend(
            [
                "",
                "## Artifacts",
                "",
                "| Artifact | Value |",
                "|---|---|",
                f"| Run Directory | `{artifact_manifest.get('run_dir')}` |",
                f"| Summary | {_markdown_link(artifact_manifest.get('summary'))} |",
                f"| Report | {_markdown_link(artifact_manifest.get('report'))} |",
                f"| Actions | {_markdown_link(artifact_manifest.get('actions'))} |",
                f"| Semantic Trace | {_markdown_link(artifact_manifest.get('semantic_trace'))} |",
                f"| Replay Draft | {_markdown_link(artifact_manifest.get('replay_draft'))} |",
                f"| Final Screenshot | {_markdown_link(artifact_manifest.get('final_screenshot'))} |",
                f"| Screenshot Count | `{artifact_manifest.get('screenshots_count', summary.get('screenshot_count'))}` |",
            ]
        )

        if testcase is not None:
            lines.extend(
                [
                    "",
                    "## Original Task",
                    f"- Title: `{testcase.get('title')}`",
                    f"- Params: `{runtime_context.get('params', {})}`",
                ]
            )
        elif runtime_context.get("task_title"):
            lines.extend(
                [
                    "",
                    "## Original Task",
                    f"- Title: `{runtime_context.get('task_title')}`",
                    f"- Params: `{runtime_context.get('params', {})}`",
                ]
            )

        return "\n".join(lines) + "\n"

    def build_semantic_trace(
        self,
        runtime_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        anomaly_events = _clean_anomaly_events(runtime_context.get("anomaly_events"))
        anomalies_by_step = _events_by_step(anomaly_events)
        represented_steps: set[int] = set()
        for raw_step in runtime_context.get("semantic_steps", []):
            if not isinstance(raw_step, dict):
                continue
            step: dict[str, Any] = {}
            step_index = raw_step.get("step_index")
            for key in _ALLOWED_SEMANTIC_STEP_FIELDS:
                if key not in raw_step or _is_forbidden_semantic_key(key):
                    continue
                value = raw_step.get(key)
                if key in {"visible_controls", "anomalies"}:
                    controls = _safe_semantic_list(value)
                    if controls:
                        step[key] = controls
                elif key in {"verification_passed", "recovery_attempt"}:
                    if value is not None:
                        step[key] = bool(value)
                elif key == "step_index":
                    if isinstance(value, int):
                        step[key] = value
                else:
                    text = _safe_semantic_text(value)
                    if text is not None:
                        step[key] = text
            if isinstance(step_index, int) and step_index in anomalies_by_step:
                represented_steps.add(step_index)
                events = anomalies_by_step[step_index]
                anomalies = _anomaly_names(events)
                recovery_hint = _first_recovery_hint(events)
                if anomalies:
                    step["anomalies"] = anomalies
                if recovery_hint:
                    step["recovery_hint"] = recovery_hint
            if step:
                trace.append(step)

        for step_index, events in sorted(anomalies_by_step.items()):
            if step_index in represented_steps:
                continue
            anomalies = _anomaly_names(events)
            if not anomalies:
                continue
            event = events[0]
            step: dict[str, Any] = {
                "step_index": step_index,
                "step_id": f"anomaly_step_{step_index:03d}",
                "anomalies": anomalies,
                "action_summary": "observe abnormal surface",
            }
            for field in ("product", "page_type"):
                text = _safe_semantic_text(event.get(field))
                if text:
                    step[field] = text
            recovery_hint = _first_recovery_hint(events)
            if recovery_hint:
                step["recovery_hint"] = recovery_hint
            trace.append(step)

        trace.sort(key=lambda step: int(step.get("step_index", 0)))
        return trace

    def build_replay_draft(self, runtime_context: dict[str, Any]) -> str:
        trace = self.build_semantic_trace(runtime_context)
        run_id = _safe_semantic_text(runtime_context.get("run_id")) or "ad_hoc_run"
        title = _safe_semantic_text(runtime_context.get("task_title"))
        lines = [f"# Replay Draft - Run {run_id}", ""]
        if title:
            lines.extend([f"- Task: {title}", ""])
        if not trace:
            lines.extend(
                [
                    "No semantic steps were recorded for this run.",
                    "",
                    "This file is a review artifact only. It is not executable.",
                ]
            )
            return "\n".join(lines) + "\n"

        for ordinal, step in enumerate(trace, start=1):
            lines.extend([f"## Step {ordinal}", ""])
            page = step.get("page_type") or "not_recorded"
            product = step.get("product")
            page_label = f"{product}:{page}" if product else page
            lines.append(f"- Page: {page_label}")
            controls = step.get("visible_controls", [])
            if controls:
                lines.append(f"- Visible controls: {', '.join(controls)}")
            anomalies = step.get("anomalies", [])
            if anomalies:
                lines.append(f"- Anomalies: {', '.join(anomalies)}")
            recovery_hint = step.get("recovery_hint")
            if recovery_hint:
                lines.append(f"- Recovery hint: {recovery_hint}")
            action_summary = step.get("action_summary")
            if action_summary:
                lines.append(f"- Action: {action_summary}")
            verification = step.get("verification")
            if verification:
                result = step.get("verification_passed")
                suffix = ""
                if result is not None:
                    suffix = " (passed)" if result else " (failed)"
                lines.append(f"- Verify: {verification}{suffix}")
            failure_type = step.get("failure_type")
            if failure_type:
                lines.append(f"- Failure type: {failure_type}")
            lines.append("")

        lines.append("This file is a review artifact only. It is not executable.")
        return "\n".join(lines) + "\n"

    def write_runtime_artifacts(
        self,
        testcase: dict[str, Any] | None,
        runtime_context: dict[str, Any],
    ) -> dict[str, str]:
        run_id = runtime_context["run_id"]
        summary = self.build_summary(testcase, runtime_context)
        run_dir = self.artifact_manager.ensure_run_dirs(run_id)
        semantic_trace = self.build_semantic_trace(runtime_context)
        summary["artifact_manifest"] = {
            "run_dir": str(run_dir),
            "summary": str(run_dir / "summary.json"),
            "report": str(run_dir / "report.md"),
            "actions": str(run_dir / "actions.jsonl"),
            "semantic_trace": (
                str(run_dir / "semantic_trace.json") if semantic_trace else None
            ),
            "replay_draft": (
                str(run_dir / "replay_draft.md") if semantic_trace else None
            ),
            "screenshots": summary.get("screenshots", []),
            "screenshots_count": summary.get("screenshot_count", 0),
            "final_screenshot": (
                summary.get("screenshots", [])[-1]
                if summary.get("screenshots")
                else None
            ),
        }
        report_md = self.build_markdown(summary, runtime_context, testcase=testcase)
        summary_path = self.artifact_manager.write_json(run_id, "summary.json", summary)
        report_path = self.artifact_manager.write_text(run_id, "report.md", report_md)
        actions_path = self.artifact_manager.write_actions_jsonl(
            run_id, runtime_context.get("action_logs", [])
        )
        paths = {
            "run_dir": str(run_dir),
            "summary": summary_path,
            "report": report_path,
            "actions": actions_path,
        }
        if semantic_trace:
            paths["semantic_trace"] = self.artifact_manager.write_json(
                run_id,
                "semantic_trace.json",
                semantic_trace,
            )
            paths["replay_draft"] = self.artifact_manager.write_text(
                run_id,
                "replay_draft.md",
                self.build_replay_draft(runtime_context),
            )
        return paths
