"""Track D recorder for the LLM-driven Feishu AgentS3 route."""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from gui_agents.feishu.detectors.anomaly import ANOMALY_FLAG_TO_TYPE
from gui_agents.feishu.detectors.base_state_detector import detect_base_state
from gui_agents.feishu.detectors.calendar_state_detector import detect_calendar_state
from gui_agents.feishu.detectors.docs_state_detector import detect_docs_state
from gui_agents.feishu.detectors.im_state_detector import detect_feishu_state
from gui_agents.feishu.detectors.vc_state_detector import detect_vc_state
from gui_agents.feishu.maintenance.artifact_manager import ArtifactManager
from gui_agents.feishu.reports.report_builder import ReportBuilder
from gui_agents.feishu.runtime import build_agentic_run_goal
from gui_agents.feishu.verifiers.assertion_verifier import AssertionVerifier


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def _run_id(instruction: str) -> str:
    now = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha1(instruction.encode("utf-8")).hexdigest()[:8]
    return f"s3_feishu_{now}_{digest}"


def _action_name(exec_code: str) -> str:
    lowered = exec_code.lower()
    if "click" in lowered:
        return "click"
    if "hotkey" in lowered or "press" in lowered:
        return "keyboard"
    if "type" in lowered or "pyperclip.copy" in lowered:
        return "type"
    if "wait" in lowered or "sleep" in lowered:
        return "wait"
    if "done" in lowered:
        return "done"
    if "fail" in lowered:
        return "fail"
    return "exec"


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_visible_controls(value: list[str] | None) -> list[str] | None:
    if not value:
        return None
    controls = [_clean_optional_text(item) for item in value]
    return [item for item in controls if item] or None


def _semantic_action_summary(action: str, status: str) -> str:
    if action == "done":
        return "agent marked task done"
    if action == "fail":
        return "agent marked task failed"
    if action == "wait":
        return "wait for interface update"
    if action == "keyboard":
        return "keyboard interaction"
    if action == "type":
        return "text input"
    if action == "click":
        return "click visible interface control"
    return f"{action} action"


def _default_priority_for_product(product: str) -> str:
    if product in {"im", "docs", "calendar", "base", "vc"}:
        return "medium"
    return "medium"


def _default_complexity_for_goal(goal: dict[str, Any]) -> str:
    task_id = str(goal.get("task_id") or "").lower()
    if any(token in task_id for token in ("cross_window", "share", "invite")):
        return "high"
    assertions = goal.get("assertions")
    assertion_count = len(assertions) if isinstance(assertions, list) else 0
    if assertion_count <= 1:
        return "low"
    if assertion_count <= 3:
        return "medium"
    return "high"


def _visible_controls_from_state(state: dict[str, Any]) -> list[str] | None:
    product_state = state.get("product_state", {})
    if not isinstance(product_state, dict):
        return None

    controls: list[str] = []
    for key, value in product_state.items():
        if value is not True:
            continue
        if not (
            key.endswith("_visible")
            or key.endswith("_ready")
            or key.endswith("_active")
        ):
            continue
        label = key
        for suffix in ("_visible", "_ready", "_active"):
            if label.endswith(suffix):
                label = label[: -len(suffix)]
                break
        controls.append(label)

    modal_type = state.get("modal_type")
    if modal_type:
        controls.append(str(modal_type))
    return sorted(dict.fromkeys(controls)) or None


class S3RuntimeRecorder:
    """Record AgentS3 runtime facts without controlling the agent."""

    def __init__(self, artifact_root: str | None = None) -> None:
        self.artifact_manager = ArtifactManager(root_dir=artifact_root)
        self.report_builder = ReportBuilder(self.artifact_manager)
        self.assertion_verifier = AssertionVerifier()
        self.runtime: dict[str, Any] | None = None
        self.instruction: str | None = None
        self._last_observation: dict[str, Any] | None = None
        self._last_artifact_paths: dict[str, str] = {}

    def start(self, instruction: str) -> dict[str, Any]:
        self.instruction = instruction
        goal = build_agentic_run_goal(instruction)
        self.runtime = {
            "run_id": _run_id(instruction),
            "status": "running",
            "intent": "agent_s3_feishu",
            "params": {"instruction": instruction},
            "product": goal["product"],
            "priority": _default_priority_for_product(str(goal["product"])),
            "complexity": _default_complexity_for_goal(goal),
            "task_id": goal["task_id"],
            "task_title": goal["title"],
            "assertion_plan": goal["assertions"],
            "page_id": None,
            "precondition_results": [],
            "action_logs": [],
            "reflections": [],
            "screenshots": [],
            "step_results": [],
            "semantic_steps": [],
            "recovery_attempts": 0,
            "anomaly_events": [],
            "failure_type": None,
            "failure_reason": None,
            "started_at": _now_iso(),
        }
        self._sync_artifacts("started")
        return self.runtime

    def run_dir(self) -> str | None:
        if self.runtime is None:
            return None
        return str(self.artifact_manager.run_dir(str(self.runtime["run_id"])))

    def runtime_stdout_path(self) -> str | None:
        if self.runtime is None:
            return None
        run_dir = self.artifact_manager.ensure_run_dirs(str(self.runtime["run_id"]))
        return str(run_dir / "runtime_stdout.log")

    def _artifact_manifest(
        self,
        run_id: str,
        *,
        semantic_trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        run_dir = self.artifact_manager.ensure_run_dirs(run_id)
        runtime_stdout = run_dir / "runtime_stdout.log"
        runtime_stdout.touch(exist_ok=True)
        screenshots = []
        if self.runtime is not None and isinstance(
            self.runtime.get("screenshots"), list
        ):
            screenshots = self.runtime.get("screenshots", [])
        return {
            "run_dir": str(run_dir),
            "summary": str(run_dir / "summary.json"),
            "report": str(run_dir / "report.md"),
            "actions": str(run_dir / "actions.jsonl"),
            "semantic_trace": (
                str(run_dir / "semantic_trace.json")
                if semantic_trace is not None
                else None
            ),
            "replay_draft": str(run_dir / "replay_draft.md"),
            "runtime_state": str(run_dir / "runtime_state.json"),
            "runtime_stdout": str(runtime_stdout),
            "artifact_error": str(run_dir / "artifact_error.txt"),
            "screenshots": screenshots,
            "screenshots_count": len(screenshots),
            "final_screenshot": screenshots[-1] if screenshots else None,
        }

    def _fallback_summary(
        self,
        run_id: str,
        *,
        reason: str,
        error: Exception | None = None,
    ) -> dict[str, Any]:
        runtime = self.runtime or {}
        return {
            "run_id": run_id,
            "task_id": runtime.get("task_id") or "ad_hoc_task",
            "product": runtime.get("product") or "general",
            "status": runtime.get("status") or "running",
            "result": "failed" if runtime.get("status") == "failed" else "not_recorded",
            "steps": len(runtime.get("step_results", [])),
            "observed_steps": len(runtime.get("step_results", [])),
            "passed_steps": sum(
                1
                for step in runtime.get("step_results", [])
                if step.get("status") == "passed"
            ),
            "failed_steps": sum(
                1
                for step in runtime.get("step_results", [])
                if step.get("status") != "passed"
            ),
            "assertions": [],
            "screenshots": runtime.get("screenshots", []),
            "screenshot_count": len(runtime.get("screenshots", [])),
            "failure_type": runtime.get("failure_type") or "artifact_generation",
            "failure_reason": runtime.get("failure_reason")
            or (repr(error) if error else reason),
            "started_at": runtime.get("started_at"),
            "completed_at": _now_iso(),
        }

    def _write_artifact_error(self, run_id: str, message: str) -> str:
        return self.artifact_manager.write_text(run_id, "artifact_error.txt", message)

    def _sync_artifacts(self, reason: str) -> dict[str, str] | None:
        if self.runtime is None:
            return None
        run_id = str(self.runtime["run_id"])
        paths: dict[str, str] = {}
        semantic_trace: list[dict[str, Any]] = []
        try:
            semantic_trace = self.report_builder.build_semantic_trace(self.runtime)
        except Exception as exc:
            self._write_artifact_error(
                run_id,
                f"{_now_iso()} semantic trace generation failed during {reason}: {exc!r}\n",
            )

        manifest = self._artifact_manifest(run_id, semantic_trace=semantic_trace)
        try:
            summary = self.report_builder.build_summary(None, self.runtime)
        except Exception as exc:
            self._write_artifact_error(
                run_id,
                f"{_now_iso()} summary generation failed during {reason}: {exc!r}\n",
            )
            summary = self._fallback_summary(run_id, reason=reason, error=exc)

        summary["artifact_manifest"] = manifest
        summary["artifact_write_reason"] = reason

        try:
            report_md = self.report_builder.build_markdown(summary, self.runtime)
        except Exception as exc:
            self._write_artifact_error(
                run_id,
                f"{_now_iso()} report generation failed during {reason}: {exc!r}\n",
            )
            report_md = (
                "# Feishu Run Report\n\n"
                f"- Run ID: `{run_id}`\n"
                f"- Status: `{self.runtime.get('status')}`\n"
                f"- Artifact generation error: `{exc!r}`\n"
            )

        try:
            replay_draft = self.report_builder.build_replay_draft(self.runtime)
        except Exception as exc:
            self._write_artifact_error(
                run_id,
                f"{_now_iso()} replay draft generation failed during {reason}: {exc!r}\n",
            )
            replay_draft = (
                f"# Replay Draft - Run {run_id}\n\n"
                "Replay draft generation failed. See `artifact_error.txt`.\n"
            )

        try:
            paths["summary"] = self.artifact_manager.write_json(
                run_id, "summary.json", summary
            )
            paths["report"] = self.artifact_manager.write_text(
                run_id, "report.md", report_md
            )
            paths["actions"] = self.artifact_manager.write_actions_jsonl(
                run_id, self.runtime.get("action_logs", [])
            )
            paths["runtime_state"] = self.artifact_manager.write_json(
                run_id, "runtime_state.json", self.runtime
            )
            paths["semantic_trace"] = self.artifact_manager.write_json(
                run_id,
                "semantic_trace.json",
                semantic_trace,
            )
            paths["replay_draft"] = self.artifact_manager.write_text(
                run_id, "replay_draft.md", replay_draft
            )
            paths["runtime_stdout"] = manifest["runtime_stdout"]
            paths["run_dir"] = manifest["run_dir"]
            self._last_artifact_paths = paths
            return paths
        except Exception as exc:
            try:
                self._write_artifact_error(
                    run_id,
                    f"{_now_iso()} artifact persistence failed during {reason}: {exc!r}\n",
                )
            except Exception:
                pass
            print(f"FEISHU_TRACK_D_WARNING: artifact persistence failed: {exc!r}")
            return self._last_artifact_paths or None

    def _sync_live_state(self, reason: str) -> dict[str, str] | None:
        """Persist cheap live artifacts without rebuilding Markdown reports."""
        if self.runtime is None:
            return None
        run_id = str(self.runtime["run_id"])
        paths = dict(self._last_artifact_paths)
        try:
            semantic_trace = self.report_builder.build_semantic_trace(self.runtime)
        except Exception as exc:
            self._write_artifact_error(
                run_id,
                f"{_now_iso()} semantic trace generation failed during {reason}: {exc!r}\n",
            )
            semantic_trace = []

        manifest = self._artifact_manifest(run_id, semantic_trace=semantic_trace)
        try:
            summary = self.report_builder.build_summary(None, self.runtime)
        except Exception as exc:
            self._write_artifact_error(
                run_id,
                f"{_now_iso()} summary generation failed during {reason}: {exc!r}\n",
            )
            summary = self._fallback_summary(run_id, reason=reason, error=exc)

        summary["artifact_manifest"] = manifest
        summary["artifact_write_reason"] = reason

        try:
            paths["summary"] = self.artifact_manager.write_json(
                run_id, "summary.json", summary
            )
            paths["actions"] = self.artifact_manager.write_actions_jsonl(
                run_id, self.runtime.get("action_logs", [])
            )
            paths["runtime_state"] = self.artifact_manager.write_json(
                run_id, "runtime_state.json", self.runtime
            )
            paths["semantic_trace"] = self.artifact_manager.write_json(
                run_id,
                "semantic_trace.json",
                semantic_trace,
            )
            paths["runtime_stdout"] = manifest["runtime_stdout"]
            paths["run_dir"] = manifest["run_dir"]
            self._last_artifact_paths = paths
            return paths
        except Exception as exc:
            try:
                self._write_artifact_error(
                    run_id,
                    f"{_now_iso()} live artifact persistence failed during {reason}: {exc!r}\n",
                )
            except Exception:
                pass
            print(f"FEISHU_TRACK_D_WARNING: live artifact persistence failed: {exc!r}")
            return self._last_artifact_paths or None

    def record_observation(self, step_index: int, observation: dict[str, Any]) -> None:
        if self.runtime is None:
            return
        self._last_observation = observation
        self._record_anomaly_events(step_index, observation)
        screenshot = observation.get("screenshot")
        if not isinstance(screenshot, bytes):
            self._sync_live_state(f"observation_{step_index:03d}")
            return
        try:
            path = self.artifact_manager.write_screenshot(
                self.runtime["run_id"],
                f"s3_step_{step_index:03d}_observation",
                screenshot,
            )
            self.runtime["screenshots"].append(path)
        except Exception as exc:
            print(f"FEISHU_TRACK_D_WARNING: screenshot persistence failed: {exc!r}")
        self._sync_live_state(f"observation_{step_index:03d}")

    def _record_anomaly_events(
        self,
        step_index: int,
        observation: dict[str, Any],
    ) -> None:
        if self.runtime is None:
            return

        product_hint = str(self.runtime.get("product") or "unknown")
        try:
            state = self._detect_state_for_product(product_hint, observation)
        except Exception:
            return

        product_state = state.get("product_state", {})
        if not isinstance(product_state, dict):
            return

        anomaly_types = product_state.get("anomaly_types")
        if not isinstance(anomaly_types, list):
            anomaly_types = [
                anomaly_type
                for flag, anomaly_type in ANOMALY_FLAG_TO_TYPE.items()
                if product_state.get(flag) is True
            ]
        anomaly_types = [
            str(anomaly_type).strip() for anomaly_type in anomaly_types if anomaly_type
        ]
        if not anomaly_types:
            return

        events = self.runtime.setdefault("anomaly_events", [])
        existing_keys = {
            (event.get("step_index"), event.get("anomaly_type")) for event in events
        }
        product = _clean_optional_text(state.get("product")) or product_hint
        page_type = _clean_optional_text(state.get("page_type")) or "not_recorded"
        recovery_hint = _clean_optional_text(product_state.get("recovery_hint"))

        for anomaly_type in sorted(dict.fromkeys(anomaly_types)):
            event_key = (step_index, anomaly_type)
            if event_key in existing_keys:
                continue
            event: dict[str, Any] = {
                "step_index": step_index,
                "timestamp": _now_iso(),
                "product": product,
                "page_type": page_type,
                "anomaly_type": anomaly_type,
            }
            if recovery_hint:
                event["recovery_hint"] = recovery_hint
            events.append(event)
            existing_keys.add(event_key)

    def record_action(
        self,
        step_index: int,
        exec_code: str,
        status: str,
        failure_reason: str | None = None,
        reflection: str | None = None,
    ) -> None:
        if self.runtime is None:
            return
        step_id = f"s3_step_{step_index:03d}"
        action = _action_name(exec_code)
        reflection_text = _clean_optional_text(reflection)
        action_log = {
            "timestamp": _now_iso(),
            "step_id": step_id,
            "stage": "AGENT_S3_STEP",
            "action": action,
            "target": None,
            "params": {"code": exec_code},
            "status": status,
            "failure_reason": failure_reason,
        }
        if reflection_text:
            action_log["reflection"] = reflection_text
            self.runtime.setdefault("reflections", []).append(reflection_text)
        self.runtime["action_logs"].append(action_log)
        failed = bool(failure_reason) or status == "failed"
        step_result = {
            "step_id": step_id,
            "stage": "AGENT_S3_STEP",
            "action": action,
            "target": None,
            "status": "failed" if failed else "passed",
            "locator_result": {
                "matched": not failed,
                "page_id": None,
                "strategy": "agent_s3_runtime",
            },
            "verification_result": {
                "passed": not failed,
                "assertion": None,
                "evidence": [],
                "failure_reason": failure_reason,
            },
            "failure_type": "runtime" if failed else None,
            "failure_reason": failure_reason,
        }
        if reflection_text:
            step_result["reflection"] = reflection_text
        self.runtime["step_results"].append(step_result)
        if failed:
            self.runtime["status"] = "failed"
            self.runtime["failure_type"] = "runtime"
            self.runtime["failure_reason"] = failure_reason or status
        self.record_semantic_step(
            step_index,
            action_summary=_semantic_action_summary(action, status),
            verification="runtime_step",
            verification_passed=not failed,
            failure_type="runtime" if failed else None,
            recovery_attempt=bool(self.runtime.get("recovery_attempts")),
            sync=False,
        )
        self._sync_artifacts(f"action_{step_index:03d}")

    def record_semantic_step(
        self,
        step_index: int,
        *,
        product: str | None = None,
        page_type: str | None = None,
        visible_controls: list[str] | None = None,
        action_summary: str | None = None,
        verification: str | None = None,
        verification_passed: bool | None = None,
        failure_type: str | None = None,
        recovery_attempt: bool | None = None,
        sync: bool = True,
    ) -> None:
        if self.runtime is None:
            return

        inferred_state: dict[str, Any] | None = None
        if page_type is None or product is None or visible_controls is None:
            product_hint = product or self.runtime.get("product") or "unknown"
            try:
                inferred_state = self._detect_state_for_product(
                    str(product_hint),
                    self._last_observation or {},
                )
            except Exception:
                inferred_state = None

        step_id = f"s3_step_{step_index:03d}"
        step: dict[str, Any] = {
            "step_index": step_index,
            "step_id": step_id,
            "timestamp": _now_iso(),
        }
        semantic_product = _clean_optional_text(
            product
            or (inferred_state or {}).get("product")
            or self.runtime.get("product")
        )
        semantic_page = _clean_optional_text(
            page_type
            or (inferred_state or {}).get("page_type")
            or self.runtime.get("page_id")
        )
        controls = _clean_visible_controls(
            visible_controls
            if visible_controls is not None
            else _visible_controls_from_state(inferred_state or {})
        )
        if semantic_product:
            step["product"] = semantic_product
        if semantic_page and not (semantic_page == "unknown" and page_type is None):
            step["page_type"] = semantic_page
        if controls:
            step["visible_controls"] = controls
        if action_summary := _clean_optional_text(action_summary):
            step["action_summary"] = action_summary
        if verification := _clean_optional_text(verification):
            step["verification"] = verification
        if verification_passed is not None:
            step["verification_passed"] = bool(verification_passed)
        if failure_type := _clean_optional_text(failure_type):
            step["failure_type"] = failure_type
        if recovery_attempt is not None:
            step["recovery_attempt"] = bool(recovery_attempt)

        semantic_steps = self.runtime.setdefault("semantic_steps", [])
        for existing in semantic_steps:
            if existing.get("step_id") == step_id:
                existing.update(step)
                if sync:
                    self._sync_artifacts(f"semantic_step_{step_index:03d}")
                return
        semantic_steps.append(step)
        if sync:
            self._sync_artifacts(f"semantic_step_{step_index:03d}")

    def _detect_state_for_product(
        self,
        product: str,
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        if product == "vc":
            return detect_vc_state(observation)
        if product == "docs":
            return detect_docs_state(observation)
        if product == "base":
            return detect_base_state(observation)
        if product == "calendar":
            return detect_calendar_state(observation)
        return detect_feishu_state(observation)

    def _build_runtime_vc_hint_state(
        self,
        detected_state: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        if self.runtime is None:
            return None, "state_detector"
        if self.runtime.get("product") != "vc":
            return None, "state_detector"
        if detected_state.get("page_type") != "unknown":
            return None, "state_detector"
        if self.runtime.get("status") != "completed":
            return None, "state_detector"

        action_logs = self.runtime.get("action_logs", [])
        if not action_logs:
            return None, "state_detector"

        last_action = action_logs[-1]
        if last_action.get("action") != "done" or last_action.get("status") != "done":
            return None, "state_detector"

        task_id = self.runtime.get("task_id")
        if task_id in {"agentic_vc_start_meeting", "agentic_vc_join_meeting"}:
            return (
                {
                    "page_type": "vc_meeting_active",
                    "product": "vc",
                    "chat_name": None,
                    "message_input_visible": False,
                    "send_button_visible": False,
                    "search_box_visible": False,
                    "modal_type": None,
                    "last_error_banner": None,
                    "product_state": {
                        "meeting_active": True,
                        "runtime_semantic_hint": "agent_done_terminal_state",
                    },
                },
                "runtime_semantic_hint",
            )

        if task_id == "agentic_vc_open_invite_dialog":
            return (
                {
                    "page_type": "vc_invite_dialog",
                    "product": "vc",
                    "chat_name": None,
                    "message_input_visible": False,
                    "send_button_visible": False,
                    "search_box_visible": True,
                    "modal_type": "vc_invite_dialog",
                    "last_error_banner": None,
                    "product_state": {
                        "invite_dialog_visible": True,
                        "share_button_visible": True,
                        "runtime_semantic_hint": "agent_done_terminal_state",
                    },
                },
                "runtime_semantic_hint",
            )

        return None, "state_detector"

    def _record_final_assertions(self, final_observation: dict[str, Any]) -> None:
        if self.runtime is None or self.runtime.get("_final_assertions_recorded"):
            return

        assertion_plan = self.runtime.get("assertion_plan", [])
        if not assertion_plan:
            return

        product = self.runtime.get("product", "general")
        detected_state = self._detect_state_for_product(product, final_observation)
        runtime_hint_state, state_strategy = self._build_runtime_vc_hint_state(
            detected_state
        )
        state = runtime_hint_state or detected_state
        self.runtime["page_id"] = state.get("page_type")
        self.runtime["final_state_source"] = state_strategy

        failures: list[dict[str, Any]] = []
        for index, goal in enumerate(assertion_plan, start=1):
            verification = self.assertion_verifier.verify_assertion(
                goal.get("assertion"),
                state,
                final_observation,
                expected=goal.get("expected") or {},
                runtime_context=self.runtime,
            )
            passed = bool(verification.get("passed"))
            self.runtime["step_results"].append(
                {
                    "step_id": f"final_assertion_{index}",
                    "stage": "FINAL_ASSERTION",
                    "action": "verify_assertion",
                    "target": state.get("page_type"),
                    "status": "passed" if passed else "failed",
                    "locator_result": {
                        "matched": state.get("page_type") != "unknown",
                        "page_id": state.get("page_type"),
                        "strategy": state_strategy,
                    },
                    "verification_result": verification,
                    "failure_type": verification.get("failure_type"),
                    "failure_reason": verification.get("failure_reason"),
                }
            )
            if not passed:
                failures.append(verification)
        self.runtime["_final_assertions_recorded"] = True
        if failures:
            self.runtime["status"] = "failed"
            self.runtime["failure_type"] = "verification"
            self.runtime["failure_reason"] = failures[0].get("failure_reason")
        elif self.runtime.get("status") == "running":
            self.runtime["status"] = "completed"

    def finalize(
        self,
        status: str | None = None,
        failure_reason: str | None = None,
        final_observation: dict[str, Any] | None = None,
    ) -> dict[str, str] | None:
        if self.runtime is None:
            return None
        if failure_reason:
            self.runtime["status"] = "failed"
            self.runtime["failure_type"] = "runtime"
            self.runtime["failure_reason"] = failure_reason
        elif status:
            self.runtime["status"] = status
        elif self.runtime.get("status") == "running":
            self.runtime["status"] = "completed"

        if (
            final_observation
            and not failure_reason
            and self.runtime.get("status") != "failed"
        ):
            self._record_final_assertions(final_observation)

        try:
            return self._sync_artifacts("finalize")
        except Exception as exc:
            message = f"{_now_iso()} finalize artifact generation failed: {exc!r}\n"
            try:
                self._write_artifact_error(str(self.runtime["run_id"]), message)
            except Exception:
                pass
            print(f"FEISHU_TRACK_D_WARNING: artifact generation failed: {exc!r}")
            return self._last_artifact_paths or None
