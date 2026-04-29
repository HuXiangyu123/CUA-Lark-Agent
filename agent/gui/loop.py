"""Minimal observe-plan-act loop for GUI execution."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from agent.gui.capture import ScreenCapture, ScreenshotArtifact
from agent.gui.calendar_flow import (
    apply_calendar_visual_state as _calendar_apply_visual_state,
    describe_calendar_visual_state as _calendar_describe_visual_state,
    is_calendar_save_action as _calendar_is_save_action,
    is_calendar_slot_action as _calendar_is_slot_action,
    refresh_calendar_done_gate as _calendar_refresh_done_gate,
)
from agent.gui.chat_flow import (
    apply_open_chat_visual_state as _chat_apply_open_chat_visual_state,
    looks_like_chat_window_view as _chat_looks_like_window_view,
    refresh_open_chat_done_gate as _chat_refresh_done_gate,
)
from agent.gui.controller import GuiController
from agent.gui.goals import (
    classify_goal_kind as _classify_goal_kind,
    extract_calendar_event_title as _extract_calendar_event_title,
    extract_calendar_time_hint as _extract_calendar_time_hint,
    extract_first_quoted_text as _extract_first_quoted_text,
    extract_target_label as _extract_target_label,
    extract_target_message as _extract_target_message,
    looks_like_calendar_event_creation_goal as _looks_like_calendar_event_creation_goal,
    looks_like_clear_composer_goal as _looks_like_clear_composer_goal,
    looks_like_compose_without_send_goal as _looks_like_compose_without_send_goal,
    looks_like_emoji_goal as _looks_like_emoji_goal,
    looks_like_open_calendar_goal as _looks_like_open_calendar_goal,
    looks_like_open_chat_goal as _looks_like_open_chat_goal,
)
from agent.gui.langchain_agents import LangChainGuiAgentSuite
from agent.gui.message_flow import (
    apply_message_execution_state as _message_apply_execution_state,
    apply_message_visual_state as _message_apply_visual_state,
    describe_message_visual_state as _message_describe_visual_state,
    initialize_late_send_message_baseline as _message_initialize_late_send_message_baseline,
    initialize_send_message_baseline as _message_initialize_send_message_baseline,
    maybe_apply_message_compose_heuristic as _message_maybe_apply_compose_heuristic,
    refresh_message_done_gate as _message_refresh_done_gate,
    submit_gate_error as _message_submit_gate_error,
)
from agent.gui.prompts import (
    GUI_ACTION_SYSTEM_PROMPT,
    GUI_PERCEPTION_SYSTEM_PROMPT,
    build_gui_user_prompt,
    build_gui_perception_prompt,
)
from agent.gui.schema import GuiDecision
from agent.gui.trace import TraceRecorder
from agent.gui.window import MacOSWindowManager, translate_action_from_image_to_screen


_ACTION_TYPES = {
    "click",
    "double_click",
    "right_click",
    "drag",
    "scroll",
    "type",
    "hotkey",
    "wait",
}


@dataclass
class GuiRunResult:
    success: bool
    final_status: str
    final_reason: str
    trace_dir: Path
    step_count: int

    def to_console_text(self) -> str:
        return (
            f"GUI run finished with status={self.final_status}, "
            f"steps={self.step_count}, trace={self.trace_dir}, reason={self.final_reason}"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "final_status": self.final_status,
            "final_reason": self.final_reason,
            "trace_dir": str(self.trace_dir),
            "step_count": self.step_count,
        }


@dataclass
class GuiRunState:
    goal_kind: str
    target_message: str
    pending_message_text: str
    target_label: str
    calendar_event_title_target: str
    calendar_target_time_hint: str
    baseline_observation_path: str
    baseline_initialized: bool = False
    baseline_latest_visible_message: str = ""
    baseline_sent_message_exact_match: bool = False
    baseline_composer_text: str = ""
    baseline_composer_nonempty: bool = False
    baseline_composer_exact_match: bool = False
    current_stage: str = "baseline_captured"
    planner_stage: str = "observe"
    previous_step_ok: bool | None = None
    compose_actions: int = 0
    submit_actions: int = 0
    clear_actions: int = 0
    perception_stage: str = "observe"
    perception_signature: str = ""
    perception_repeat_count: int = 0
    perception_stable_after: int = 2
    perception_stable: bool = False
    perception_confidence: float = 0.0
    target_message_typed: bool = False
    target_message_visually_verified: bool = False
    emoji_composed: bool = False
    send_visually_confirmed: bool = False
    typed_texts: list[str] = field(default_factory=list)
    completion_evidence: list[str] = field(default_factory=list)
    last_visual_state: dict[str, Any] = field(default_factory=dict)
    last_visual_evidence: str = ""
    done_gate_ready: bool = False
    done_gate_reason: str = ""
    composer_reset_required: bool = False
    composer_reset_started: bool = False
    composer_reset_satisfied: bool = False
    navigation_actions: int = 0
    chat_target_open_verified: bool = False
    calendar_visible_verified: bool = False
    calendar_today_highlighted_verified: bool = False
    calendar_today_label: str = ""
    calendar_event_editor_verified: bool = False
    calendar_slot_action_count: int = 0
    calendar_event_title_typed_verified: bool = False
    calendar_event_title_current: str = ""
    calendar_time_range_verified: bool = False
    calendar_save_actions: int = 0
    calendar_event_saved_verified: bool = False
    calendar_preexisting_matching_event_visible: bool = False
    workflow_steps: list[str] = field(default_factory=list)
    workflow_active_step_index: int | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "goal_kind": self.goal_kind,
            "target_message": self.target_message,
            "pending_message_text": self.pending_message_text,
            "target_label": self.target_label,
            "calendar_event_title_target": self.calendar_event_title_target,
            "calendar_target_time_hint": self.calendar_target_time_hint,
            "baseline_observation_path": self.baseline_observation_path,
            "baseline_initialized": self.baseline_initialized,
            "baseline_latest_visible_message": self.baseline_latest_visible_message,
            "baseline_sent_message_exact_match": self.baseline_sent_message_exact_match,
            "baseline_composer_text": self.baseline_composer_text,
            "baseline_composer_nonempty": self.baseline_composer_nonempty,
            "baseline_composer_exact_match": self.baseline_composer_exact_match,
            "current_stage": self.current_stage,
            "planner_stage": self.planner_stage,
            "previous_step_ok": self.previous_step_ok,
            "compose_actions": self.compose_actions,
            "submit_actions": self.submit_actions,
            "clear_actions": self.clear_actions,
            "perception_stage": self.perception_stage,
            "perception_signature": self.perception_signature,
            "perception_repeat_count": self.perception_repeat_count,
            "perception_stable_after": self.perception_stable_after,
            "perception_stable": self.perception_stable,
            "perception_confidence": self.perception_confidence,
            "target_message_typed": self.target_message_typed,
            "target_message_visually_verified": self.target_message_visually_verified,
            "emoji_composed": self.emoji_composed,
            "send_visually_confirmed": self.send_visually_confirmed,
            "typed_texts": list(self.typed_texts),
            "completion_evidence": list(self.completion_evidence),
            "last_visual_state": dict(self.last_visual_state),
            "last_visual_evidence": self.last_visual_evidence,
            "done_gate_ready": self.done_gate_ready,
            "done_gate_reason": self.done_gate_reason,
            "composer_reset_required": self.composer_reset_required,
            "composer_reset_started": self.composer_reset_started,
            "composer_reset_satisfied": self.composer_reset_satisfied,
            "navigation_actions": self.navigation_actions,
            "chat_target_open_verified": self.chat_target_open_verified,
            "calendar_visible_verified": self.calendar_visible_verified,
            "calendar_today_highlighted_verified": self.calendar_today_highlighted_verified,
            "calendar_today_label": self.calendar_today_label,
            "calendar_event_editor_verified": self.calendar_event_editor_verified,
            "calendar_slot_action_count": self.calendar_slot_action_count,
            "calendar_event_title_typed_verified": self.calendar_event_title_typed_verified,
            "calendar_event_title_current": self.calendar_event_title_current,
            "calendar_time_range_verified": self.calendar_time_range_verified,
            "calendar_save_actions": self.calendar_save_actions,
            "calendar_event_saved_verified": self.calendar_event_saved_verified,
            "calendar_preexisting_matching_event_visible": self.calendar_preexisting_matching_event_visible,
            "workflow_steps": _serialize_workflow_steps(self),
            "baseline_guardrail": "Visible old chat content does not count as completion for this run.",
        }


@dataclass
class GuiPerceptionState:
    stage: str = "observe"
    ui_summary: str = ""
    primary_view: str = ""
    selected_sidebar_item: str = ""
    chat_title: str = ""
    composer_visible: bool = False
    composer_focused: bool = False
    composer_text: str = ""
    composer_placeholder: str = ""
    composer_exact_match: bool = False
    composer_empty: bool = False
    send_button_visible: bool = False
    sent_message_visible: bool = False
    sent_message_exact_match: bool = False
    latest_visible_message: str = ""
    calendar_visible: bool = False
    calendar_today_highlighted: bool = False
    calendar_today_label: str = ""
    calendar_event_editor_visible: bool = False
    calendar_event_editor_title_text: str = ""
    calendar_event_time_range: str = ""
    calendar_save_button_visible: bool = False
    calendar_saved_event_visible: bool = False
    calendar_saved_event_title: str = ""
    blocked: bool = False
    confidence: float = 0.0
    evidence: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuiPerceptionState":
        return cls(
            stage=str(data.get("stage", "observe")).strip() or "observe",
            ui_summary=str(data.get("ui_summary", "")).strip(),
            primary_view=str(data.get("primary_view", "")).strip(),
            selected_sidebar_item=str(data.get("selected_sidebar_item", "")).strip(),
            chat_title=str(data.get("chat_title", "")).strip(),
            composer_visible=bool(data.get("composer_visible", False)),
            composer_focused=bool(data.get("composer_focused", False)),
            composer_text=str(data.get("composer_text", "")).strip(),
            composer_placeholder=str(data.get("composer_placeholder", "")).strip(),
            composer_exact_match=bool(data.get("composer_exact_match", False)),
            composer_empty=bool(data.get("composer_empty", False)),
            send_button_visible=bool(data.get("send_button_visible", False)),
            sent_message_visible=bool(data.get("sent_message_visible", False)),
            sent_message_exact_match=bool(data.get("sent_message_exact_match", False)),
            latest_visible_message=str(data.get("latest_visible_message", "")).strip(),
            calendar_visible=bool(data.get("calendar_visible", False)),
            calendar_today_highlighted=bool(data.get("calendar_today_highlighted", False)),
            calendar_today_label=str(data.get("calendar_today_label", "")).strip(),
            calendar_event_editor_visible=bool(data.get("calendar_event_editor_visible", False)),
            calendar_event_editor_title_text=str(data.get("calendar_event_editor_title_text", "")).strip(),
            calendar_event_time_range=str(data.get("calendar_event_time_range", "")).strip(),
            calendar_save_button_visible=bool(data.get("calendar_save_button_visible", False)),
            calendar_saved_event_visible=bool(data.get("calendar_saved_event_visible", False)),
            calendar_saved_event_title=str(data.get("calendar_saved_event_title", "")).strip(),
            blocked=bool(data.get("blocked", False)),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            evidence=str(data.get("evidence", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ui_summary": self.ui_summary,
            "primary_view": self.primary_view,
            "selected_sidebar_item": self.selected_sidebar_item,
            "chat_title": self.chat_title,
            "composer_visible": self.composer_visible,
            "composer_focused": self.composer_focused,
            "composer_text": self.composer_text,
            "composer_placeholder": self.composer_placeholder,
            "composer_exact_match": self.composer_exact_match,
            "composer_empty": self.composer_empty,
            "send_button_visible": self.send_button_visible,
            "sent_message_visible": self.sent_message_visible,
            "sent_message_exact_match": self.sent_message_exact_match,
            "latest_visible_message": self.latest_visible_message,
            "calendar_visible": self.calendar_visible,
            "calendar_today_highlighted": self.calendar_today_highlighted,
            "calendar_today_label": self.calendar_today_label,
            "calendar_event_editor_visible": self.calendar_event_editor_visible,
            "calendar_event_editor_title_text": self.calendar_event_editor_title_text,
            "calendar_event_time_range": self.calendar_event_time_range,
            "calendar_save_button_visible": self.calendar_save_button_visible,
            "calendar_saved_event_visible": self.calendar_saved_event_visible,
            "calendar_saved_event_title": self.calendar_saved_event_title,
            "blocked": self.blocked,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }

    def signature(self, target_message: str) -> str:
        normalized_target = _normalize_text(target_message)
        normalized_composer = _normalize_text(self.composer_text)
        normalized_latest = _normalize_text(self.latest_visible_message)
        normalized_editor_title = _normalize_text(self.calendar_event_editor_title_text)
        normalized_saved_title = _normalize_text(self.calendar_saved_event_title)
        return "|".join(
            [
                self.stage,
                "composer_exact" if self.composer_exact_match else "composer_not_exact",
                "composer_empty" if self.composer_empty else "composer_filled",
                "sent_exact" if self.sent_message_exact_match else "sent_not_exact",
                _normalize_text(self.primary_view),
                _normalize_text(self.selected_sidebar_item),
                "calendar_visible" if self.calendar_visible else "calendar_not_visible",
                "calendar_today" if self.calendar_today_highlighted else "calendar_not_today",
                "calendar_editor" if self.calendar_event_editor_visible else "calendar_editor_not_visible",
                "calendar_saved_event" if self.calendar_saved_event_visible else "calendar_saved_event_not_visible",
                "blocked" if self.blocked else "not_blocked",
                normalized_editor_title,
                normalized_saved_title,
                normalized_composer,
                normalized_latest,
                normalized_target,
            ]
        )


GuiMessageVisualState = GuiPerceptionState


class GuiRunner:
    """High-level GUI loop driven by a multimodal model."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        *,
        max_steps: int | None = None,
        dry_run: bool | None = None,
        pause_seconds: float | None = None,
        trace_root: Path | None = None,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.client = _build_gui_client(client)
        self.model = _first_nonempty_env(("GUI_VLM_MODEL", "VLM_MODEL", "CUA_MODEL"), model)
        self.max_steps = max_steps or int(_first_nonempty_env(("GUI_MAX_STEPS", "CUA_MAX_STEPS"), "12"))
        self.dry_run = dry_run if dry_run is not None else _env_flag(("GUI_DRY_RUN", "CUA_DRY_RUN"), False)
        self.pause_seconds = pause_seconds or float(_first_nonempty_env(("GUI_ACTION_PAUSE", "CUA_ACTION_PAUSE"), "0.5"))
        self.min_perception_confidence = float(
            _first_nonempty_env(("GUI_MIN_PERCEPTION_CONFIDENCE", "CUA_MIN_PERCEPTION_CONFIDENCE"), "0.25")
        )
        self.target_app = _first_nonempty_env(("GUI_TARGET_APP", "CUA_TARGET_APP"), "Feishu")
        trace_root_value = trace_root or Path(_first_nonempty_env(("GUI_TRACE_DIR", "CUA_TRACE_DIR"), "traces"))
        self.trace_root = trace_root_value
        self.capture = ScreenCapture()
        self.controller = GuiController(dry_run=self.dry_run, pause_seconds=self.pause_seconds)
        self.window_manager = MacOSWindowManager()
        self.progress_hook = progress_hook
        self.route_agents = LangChainGuiAgentSuite(
            model=self.model,
            api_key=_first_nonempty_env(("GUI_VLM_API_KEY", "VLM_API_KEY", "CUA_API_KEY", "OPENAI_API_KEY"), ""),
            base_url=_first_nonempty_env(("GUI_VLM_API_BASE", "VLM_API_BASE", "CUA_API_BASE", "OPENAI_API_BASE"), "").rstrip("/") or None,
            perception_system_prompt=GUI_PERCEPTION_SYSTEM_PROMPT,
            action_system_prompt=GUI_ACTION_SYSTEM_PROMPT,
        )

    def run(self, goal: str) -> GuiRunResult:
        recorder = TraceRecorder(self.trace_root, goal, self.model)
        history: list[dict[str, Any]] = []

        window = self.window_manager.activate_and_get_window(self.target_app)
        observation = self.capture.capture(recorder.trace_dir, "step_00_observe", region=window.region)
        run_state = _build_initial_run_state(goal, observation)
        initial_perception_raw = self._refresh_visual_state(goal, observation, history, window.app_name, run_state)
        recorder.write_text("step_00_perception.json", initial_perception_raw)
        recorder.set_initial_state(run_state.snapshot())
        visual_stop_reason = self._visual_stop_reason(run_state)
        if visual_stop_reason:
            recorder.finish("blocked", visual_stop_reason, run_state.snapshot())
            self._emit_progress(
                recorder,
                run_state,
                event="finished",
                step_index=0,
                success=False,
                message=visual_stop_reason,
            )
            return GuiRunResult(False, "blocked", visual_stop_reason, recorder.trace_dir, len(history))
        self._emit_progress(recorder, run_state, event="started", step_index=0, message="Captured the initial Feishu window and built the first visual state.")
        for step_index in range(1, self.max_steps + 1):
            decision, raw_response = self._plan(goal, observation, history, step_index, window.app_name, run_state)
            recorder.write_text(f"step_{step_index:02d}_planner.json", raw_response)
            _apply_decision_state(run_state, decision)
            self._emit_progress(
                recorder,
                run_state,
                event="decision",
                step_index=step_index,
                decision=decision,
                message=decision.success_criteria or decision.progress_assessment,
            )

            if decision.status == "done":
                reason = decision.done_reason or decision.progress_assessment or "goal completed"
                recorder.finish("done", reason, run_state.snapshot())
                self._emit_progress(
                    recorder,
                    run_state,
                    event="finished",
                    step_index=step_index,
                    decision=decision,
                    success=True,
                    message=reason,
                )
                return GuiRunResult(True, "done", reason, recorder.trace_dir, len(history))

            if decision.status == "blocked":
                reason = decision.done_reason or decision.progress_assessment or "planner blocked"
                run_state.current_stage = "blocked"
                recorder.finish("blocked", reason, run_state.snapshot())
                self._emit_progress(
                    recorder,
                    run_state,
                    event="finished",
                    step_index=step_index,
                    decision=decision,
                    success=False,
                    message=reason,
                )
                return GuiRunResult(False, "blocked", reason, recorder.trace_dir, len(history))

            state_before_action = run_state.snapshot()
            screen_action = translate_action_from_image_to_screen(decision.action, observation)
            execution = self.controller.execute(screen_action)
            _apply_execution_state(run_state, decision, execution)
            window = self.window_manager.activate_and_get_window(self.target_app)
            observation = self.capture.capture(recorder.trace_dir, f"step_{step_index:02d}_after", region=window.region)
            perception_raw = self._refresh_visual_state(goal, observation, history, window.app_name, run_state)
            recorder.write_text(f"step_{step_index:02d}_perception.json", perception_raw)
            visual_stop_reason = self._visual_stop_reason(run_state)
            if visual_stop_reason:
                step_record = {
                    "step_index": step_index,
                    "observation_path": str(observation.path),
                    "observation_size": {"width": observation.width, "height": observation.height},
                    "window": {
                        "app_name": window.app_name,
                        "x": window.x,
                        "y": window.y,
                        "width": window.width,
                        "height": window.height,
                    },
                    "decision": decision.to_dict(),
                    "action": decision.action.to_dict() if decision.action else None,
                    "screen_action": screen_action.to_dict() if screen_action else None,
                    "execution": execution.to_dict(),
                    "visual_state": dict(run_state.last_visual_state),
                    "state_before_action": state_before_action,
                    "state_after_action": run_state.snapshot(),
                    "blocked_reason": visual_stop_reason,
                }
                history.append(step_record)
                recorder.append_step(step_record)
                recorder.finish("blocked", visual_stop_reason, run_state.snapshot())
                self._emit_progress(
                    recorder,
                    run_state,
                    event="finished",
                    step_index=step_index,
                    decision=decision,
                    execution=execution,
                    success=False,
                    message=visual_stop_reason,
                )
                return GuiRunResult(False, "blocked", visual_stop_reason, recorder.trace_dir, len(history))

            step_record = {
                "step_index": step_index,
                "observation_path": str(observation.path),
                "observation_size": {"width": observation.width, "height": observation.height},
                "window": {
                    "app_name": window.app_name,
                    "x": window.x,
                    "y": window.y,
                    "width": window.width,
                    "height": window.height,
                },
                "decision": decision.to_dict(),
                "action": decision.action.to_dict() if decision.action else None,
                "screen_action": screen_action.to_dict() if screen_action else None,
                "execution": execution.to_dict(),
                "visual_state": dict(run_state.last_visual_state),
                "state_before_action": state_before_action,
                "state_after_action": run_state.snapshot(),
            }
            history.append(step_record)
            recorder.append_step(step_record)
            self._emit_progress(
                recorder,
                run_state,
                event="step_completed",
                step_index=step_index,
                decision=decision,
                execution=execution,
                message=run_state.done_gate_reason,
            )

            if decision.action and decision.action.target == "feishu submit composed emoji (heuristic)":
                reason = "Feishu emoji heuristic flow completed."
                run_state.current_stage = "complete"
                recorder.finish("done", reason, run_state.snapshot())
                return GuiRunResult(True, "done", reason, recorder.trace_dir, len(history))

        reason = f"reached max steps ({self.max_steps})"
        recorder.finish("max_steps_exceeded", reason, run_state.snapshot())
        self._emit_progress(
            recorder,
            run_state,
            event="finished",
            step_index=self.max_steps,
            success=False,
            message=reason,
        )
        return GuiRunResult(False, "max_steps_exceeded", reason, recorder.trace_dir, len(history))

    def _visual_stop_reason(self, run_state: GuiRunState) -> str:
        visual_state = run_state.last_visual_state
        if not visual_state:
            return ""
        evidence = run_state.last_visual_evidence or str(visual_state.get("ui_summary", "")).strip()
        if bool(visual_state.get("blocked", False)) or str(visual_state.get("stage", "")).strip().lower() == "blocked":
            run_state.current_stage = "blocked"
            return evidence or "The perception model marked the current screen as blocked or unusable."
        if self.min_perception_confidence > 0 and run_state.perception_confidence < self.min_perception_confidence:
            run_state.current_stage = "blocked"
            return (
                f"Perception confidence is too low ({run_state.perception_confidence:.2f} "
                f"< {self.min_perception_confidence:.2f}); pausing before any further GUI actions. "
                f"{evidence}".strip()
            )
        return ""

    def _emit_progress(
        self,
        recorder: TraceRecorder,
        run_state: GuiRunState,
        *,
        event: str,
        step_index: int,
        decision: GuiDecision | None = None,
        execution: Any | None = None,
        success: bool | None = None,
        message: str = "",
    ) -> None:
        if self.progress_hook is None:
            return
        payload = {
            "event": event,
            "trace_dir": str(recorder.trace_dir),
            "step_index": step_index,
            "max_steps": self.max_steps,
            "goal_kind": run_state.goal_kind,
            "target_message": run_state.target_message,
            "target_label": run_state.target_label,
            "current_stage": run_state.current_stage,
            "planner_stage": run_state.planner_stage,
            "perception_stage": run_state.perception_stage,
            "perception_stable": run_state.perception_stable,
            "compose_actions": run_state.compose_actions,
            "submit_actions": run_state.submit_actions,
            "clear_actions": run_state.clear_actions,
            "done_gate_ready": run_state.done_gate_ready,
            "done_gate_reason": run_state.done_gate_reason,
            "baseline_composer_dirty": run_state.baseline_composer_nonempty,
            "composer_reset_required": run_state.composer_reset_required,
            "composer_reset_satisfied": run_state.composer_reset_satisfied,
            "workflow_steps": _serialize_workflow_steps(run_state, decision_status=decision.status if decision else None, success=success),
            "decision_status": decision.status if decision else None,
            "action_type": decision.action.type if decision and decision.action else None,
            "action_target": decision.action.target if decision and decision.action else None,
            "result_ok": getattr(execution, "ok", None) if execution is not None else None,
            "success": success,
            "message": message,
        }
        self.progress_hook(payload)

    def _refresh_visual_state(
        self,
        goal: str,
        observation: ScreenshotArtifact,
        history: list[dict[str, Any]],
        app_name: str,
        run_state: GuiRunState,
    ) -> str:
        perception_state, raw_response = self._perceive(goal, observation, history, app_name, run_state)
        _apply_visual_state(run_state, perception_state)
        return raw_response

    def _plan(
        self,
        goal: str,
        observation: ScreenshotArtifact,
        history: list[dict[str, Any]],
        step_index: int,
        app_name: str,
        run_state: GuiRunState,
    ) -> tuple[GuiDecision, str]:
        if _env_flag(("GUI_ENABLE_EMOJI_HEURISTIC", "CUA_ENABLE_EMOJI_HEURISTIC"), False):
            heuristic_decision = _maybe_apply_feishu_emoji_heuristic(goal, observation, history, step_index, app_name)
            if heuristic_decision is not None:
                return heuristic_decision, json.dumps(heuristic_decision.to_dict(), ensure_ascii=False, indent=2)
        heuristic_decision = _maybe_apply_message_compose_heuristic(observation, history, run_state)
        if heuristic_decision is not None:
            return heuristic_decision, json.dumps(heuristic_decision.to_dict(), ensure_ascii=False, indent=2)
        if run_state.goal_kind == "clear_composer":
            heuristic_decision = _maybe_apply_clear_composer_heuristic(observation, history, run_state)
            if heuristic_decision is not None:
                return heuristic_decision, json.dumps(heuristic_decision.to_dict(), ensure_ascii=False, indent=2)

        history_summary = _summarize_history(history)
        run_state_summary = _summarize_run_state(run_state)
        data_url = _image_to_data_url(observation.path)
        retry_note = ""
        last_error = ""
        last_content = ""
        for attempt in range(3):
            prompt = build_gui_user_prompt(
                goal=goal,
                step_index=step_index,
                max_steps=self.max_steps,
                screenshot_width=observation.width,
                screenshot_height=observation.height,
                app_name=app_name,
                window_origin_x=observation.origin_x,
                window_origin_y=observation.origin_y,
                history_summary=history_summary,
                run_state_summary=run_state_summary,
            )
            if retry_note:
                prompt = f"{prompt}\n\nPlanner correction:\n{retry_note}"

            try:
                action_decision, raw_response = self.route_agents.decide(prompt, data_url)
                payload = action_decision.model_dump()
                decision = GuiDecision.from_dict(payload)
                last_content = raw_response
            except ValueError as exc:
                last_error = f"planner returned invalid decision schema: {exc}"
                retry_note = (
                    "Your previous response used the wrong JSON schema. Return a top-level object with "
                    'status="continue|done|blocked", plus stage, current_state, progress_assessment, '
                    "success_criteria, optional completion_evidence, optional done_reason, and an action object when status=continue."
                )
                continue
            except Exception as exc:
                last_error = f"planner invocation failed: {exc}"
                retry_note = "Your previous response failed validation or invocation. Return a valid structured action decision."
                continue
            bounds_error = _decision_bounds_error(decision, observation)
            submit_gate_error = _submit_gate_error(decision, run_state)
            done_gate_error = _done_gate_error(decision, run_state)
            blocked_gate_error = _blocked_gate_error(decision, run_state)
            if (
                bounds_error is None
                and submit_gate_error is None
                and done_gate_error is None
                and blocked_gate_error is None
            ):
                return decision, last_content

            if submit_gate_error == "The composer exact-match observation is not stable yet. Re-observe once before submitting.":
                wait_decision = GuiDecision.from_dict(
                    {
                        "status": "continue",
                        "stage": "verify",
                        "current_state": decision.current_state or "Exact target text is visible in the composer but the observation is not stable yet.",
                        "progress_assessment": "Deferring submit by one step so the GUI loop can capture one more verification frame.",
                        "previous_step_ok": True,
                        "success_criteria": "A repeated observation should confirm the exact target text remains visible before submit.",
                        "completion_evidence": decision.completion_evidence or "Submit was deferred because the exact-match composer observation was not stable yet.",
                        "action": {
                            "type": "wait",
                            "target": "allow one more stable verification frame before submit",
                            "duration_ms": 800,
                        },
                    }
                )
                synthetic_response = json.dumps(wait_decision.to_dict(), ensure_ascii=False, indent=2)
                return wait_decision, synthetic_response

            if done_gate_error == "The visual completion signal is not stable across observations yet.":
                wait_decision = GuiDecision.from_dict(
                    {
                        "status": "continue",
                        "stage": "verify",
                        "current_state": decision.current_state or "The goal appears complete, but one more stable verification frame is required.",
                        "progress_assessment": "Deferring completion by one step so the GUI loop can capture one more stable post-send observation.",
                        "previous_step_ok": True,
                        "success_criteria": "A repeated observation should keep showing the cleared composer or newly sent exact target message.",
                        "completion_evidence": decision.completion_evidence or "Completion was deferred because the visual success signal was not stable yet.",
                        "workflow_steps": decision.workflow_steps,
                        "active_step_index": decision.active_step_index,
                        "action": {
                            "type": "wait",
                            "target": "allow one more stable verification frame after send",
                            "duration_ms": 800,
                        },
                    }
                )
                synthetic_response = json.dumps(wait_decision.to_dict(), ensure_ascii=False, indent=2)
                return wait_decision, synthetic_response

            last_error = bounds_error or submit_gate_error or done_gate_error or blocked_gate_error or "planner returned an invalid decision"
            if bounds_error is not None:
                retry_note = (
                    f"Your previous action was invalid: {bounds_error}. "
                    f"Return a corrected JSON action with coordinates inside x=0..{observation.width - 1}, "
                    f"y=0..{observation.height - 1}, using the screenshot pixel grid."
                )
            elif submit_gate_error is not None:
                retry_note = (
                    f"Your previous submit action was rejected: {submit_gate_error}. "
                    "Do not submit partial or mismatched text. Correct the composer contents first, then submit."
                )
            elif blocked_gate_error is not None:
                retry_note = (
                    f"Your previous blocked decision was rejected: {blocked_gate_error}. "
                    "A pre-existing matching calendar event does not satisfy this run. "
                    "Choose a concrete next action that advances the fresh create flow: click the requested time row "
                    "in today's column, type the exact title, click Save, then verify the newly created event."
                )
            else:
                retry_note = (
                    f"Your previous done decision was rejected: {done_gate_error}. "
                    "Do not rely on old visible chat content. Use the run-state and execution history, then return "
                    'either status="continue" with the next safe action or status="blocked" if no safe next action exists.'
                )

        raise RuntimeError(f"{last_error}\nLast planner output: {last_content}")

    def _perceive(
        self,
        goal: str,
        observation: ScreenshotArtifact,
        history: list[dict[str, Any]],
        app_name: str,
        run_state: GuiRunState,
    ) -> tuple[GuiPerceptionState, str]:
        history_summary = _summarize_history(history)
        run_state_summary = _summarize_run_state(run_state)
        data_url = _image_to_data_url(observation.path)
        prompt = build_gui_perception_prompt(
            goal=goal,
            screenshot_width=observation.width,
            screenshot_height=observation.height,
            app_name=app_name,
            history_summary=history_summary,
            run_state_summary=run_state_summary,
        )
        last_error = ""
        last_content = ""
        for attempt in range(3):
            try:
                perception_state, raw_response = self.route_agents.perceive(prompt, data_url)
                last_content = raw_response
                return GuiPerceptionState.from_dict(perception_state.model_dump()), raw_response
            except Exception as exc:
                last_error = f"perception agent failed: {exc}"
                continue
        raise RuntimeError(f"{last_error}\nLast perception output: {last_content}")


def _coerce_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text", "")))
            elif hasattr(item, "text"):
                texts.append(str(item.text))
        return "\n".join(part for part in texts if part)
    return str(content)


def _normalize_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status", "")).strip().lower()
    if status in {"continue", "done", "blocked"}:
        return payload

    nested_action = payload.get("action")
    if isinstance(nested_action, dict):
        normalized = dict(payload)
        normalized["status"] = "continue"
        normalized["stage"] = str(normalized.get("stage", "")).strip() or "act"
        normalized["progress_assessment"] = normalized.get("progress_assessment") or "Planner returned an action."
        normalized["success_criteria"] = normalized.get("success_criteria") or "Execute the next GUI action safely."
        normalized["completion_evidence"] = str(normalized.get("completion_evidence", "")).strip()
        return normalized

    action_type = status if status in _ACTION_TYPES else str(payload.get("type", "")).strip().lower()
    if action_type not in _ACTION_TYPES:
        return payload

    action = {
        "type": action_type,
        "target": payload.get("target", ""),
        "x": payload.get("x"),
        "y": payload.get("y"),
        "end_x": payload.get("end_x"),
        "end_y": payload.get("end_y"),
        "text": payload.get("text"),
        "keys": payload.get("keys"),
        "scroll_amount": payload.get("scroll_amount"),
        "duration_ms": payload.get("duration_ms"),
    }
    return {
        "status": "continue",
        "stage": str(payload.get("stage", "")).strip() or "act",
        "current_state": str(payload.get("current_state", "")).strip(),
        "progress_assessment": str(payload.get("progress_assessment", "")).strip() or "Planner returned a single GUI action.",
        "previous_step_ok": payload.get("previous_step_ok"),
        "success_criteria": str(payload.get("success_criteria", "")).strip() or f"Execute the {action_type} action safely.",
        "completion_evidence": str(payload.get("completion_evidence", "")).strip(),
        "done_reason": str(payload.get("done_reason", "")).strip(),
        "workflow_steps": payload.get("workflow_steps", []),
        "active_step_index": payload.get("active_step_index"),
        "action": action,
    }


def _maybe_apply_message_compose_heuristic(
    observation: ScreenshotArtifact,
    history: list[dict[str, Any]],
    run_state: GuiRunState,
) -> GuiDecision | None:
    return _message_maybe_apply_compose_heuristic(
        observation,
        history,
        run_state,
        decision_from_dict=GuiDecision.from_dict,
    )


def _maybe_apply_clear_composer_heuristic(
    observation: ScreenshotArtifact,
    history: list[dict[str, Any]],
    run_state: GuiRunState,
) -> GuiDecision | None:
    visual_state = run_state.last_visual_state or {}
    if bool(visual_state.get("composer_empty", False)):
        return GuiDecision.from_dict(
            {
                "status": "done",
                "stage": "complete",
                "current_state": "The composer is visually empty.",
                "progress_assessment": "The draft has been cleared and no send action occurred.",
                "previous_step_ok": True,
                "success_criteria": "The current chat input box contains no draft text and no message is sent.",
                "completion_evidence": run_state.last_visual_evidence or "The screenshot shows an empty composer.",
                "done_reason": "The composer is empty and no send/submit action occurred.",
                "workflow_steps": ["Focus composer", "Select all draft text", "Delete draft", "Verify empty composer"],
                "active_step_index": 3,
            }
        )

    recent_actions = [
        ((item.get("action") or {}).get("target") or "")
        for item in history
        if isinstance(item, dict)
    ]
    focus_target = "clear composer focus"
    select_target = "clear composer select all"
    delete_target = "clear composer delete selection"
    focus_count = recent_actions.count(focus_target)
    select_count = recent_actions.count(select_target)
    delete_count = recent_actions.count(delete_target)
    max_delete_attempts = int(_first_nonempty_env(("GUI_CLEAR_MAX_DELETE_ATTEMPTS", "CUA_CLEAR_MAX_DELETE_ATTEMPTS"), "3"))
    if delete_count >= max_delete_attempts:
        visible_text = str(visual_state.get("composer_text", "")).strip()
        return GuiDecision.from_dict(
            {
                "status": "blocked",
                "stage": "blocked",
                "current_state": f"The composer still appears non-empty after {delete_count} delete attempts.",
                "progress_assessment": "The deterministic clear shortcut did not clear the draft.",
                "previous_step_ok": False,
                "success_criteria": "Manual intervention may be needed to clear the focused composer.",
                "completion_evidence": f"Visible composer text after retries: {visible_text!r}",
                "done_reason": "Could not verify an empty composer after repeated focus/Ctrl+A/Backspace attempts.",
                "workflow_steps": ["Focus composer", "Select all draft text", "Delete draft", "Verify empty composer"],
                "active_step_index": 3,
            }
        )

    if focus_count <= delete_count:
        # Click the left text-editing part of the composer. The center/right
        # side of Feishu's composer often contains toolbar buttons, and Ctrl+A
        # after clicking there can select the whole chat page instead.
        composer_x = max(24, min(observation.width - 180, int(observation.width * 0.08)))
        composer_y = max(1, observation.height - 45)
        return GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The composer may contain draft text and should be focused before clearing.",
                "progress_assessment": "Focusing the composer starts the deterministic clear flow.",
                "previous_step_ok": True,
                "success_criteria": "The message composer becomes focused so keyboard clearing shortcuts apply there.",
                "workflow_steps": ["Focus composer", "Select all draft text", "Delete draft", "Verify empty composer"],
                "active_step_index": 0,
                "action": {
                    "type": "click",
                    "target": focus_target,
                    "x": composer_x,
                    "y": composer_y,
                },
            }
        )

    if select_count <= delete_count:
        modifier = "command" if sys.platform == "darwin" else "ctrl"
        return GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The composer is focused and any draft text should be selected.",
                "progress_assessment": "Selecting all draft text avoids slow drag-selection and partial deletes.",
                "previous_step_ok": True,
                "success_criteria": "All draft text in the focused composer becomes selected.",
                "workflow_steps": ["Focus composer", "Select all draft text", "Delete draft", "Verify empty composer"],
                "active_step_index": 1,
                "action": {
                    "type": "hotkey",
                    "target": select_target,
                    "keys": [modifier, "a"],
                },
            }
        )

    if delete_count < select_count:
        return GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The composer draft should be selected.",
                "progress_assessment": "Deleting the selection should clear the composer without sending anything.",
                "previous_step_ok": True,
                "success_criteria": "The composer becomes empty or shows only its placeholder.",
                "workflow_steps": ["Focus composer", "Select all draft text", "Delete draft", "Verify empty composer"],
                "active_step_index": 2,
                "action": {
                    "type": "hotkey",
                    "target": delete_target,
                    "keys": ["backspace"],
                },
            }
        )

    return None


def _build_initial_run_state(goal: str, observation: ScreenshotArtifact) -> GuiRunState:
    goal_kind = _classify_goal_kind(goal)
    target_message = _extract_target_message(goal) if goal_kind in {"send_message", "compose_message"} else ""
    run_state = GuiRunState(
        goal_kind=goal_kind,
        target_message=target_message,
        pending_message_text=target_message,
        target_label=_extract_target_label(goal, goal_kind),
        calendar_event_title_target=_extract_calendar_event_title(goal, goal_kind),
        calendar_target_time_hint=_extract_calendar_time_hint(goal, goal_kind),
        baseline_observation_path=str(observation.path),
        perception_stable_after=max(
            1,
            int(_first_nonempty_env(("GUI_STATE_DEBOUNCE", "CUA_STATE_DEBOUNCE"), "2")),
        ),
    )
    _refresh_done_gate(run_state)
    return run_state


def _apply_decision_state(run_state: GuiRunState, decision: GuiDecision) -> None:
    run_state.planner_stage = decision.stage
    run_state.previous_step_ok = decision.previous_step_ok
    _apply_workflow_plan(run_state, decision.workflow_steps, decision.active_step_index)
    if decision.completion_evidence:
        _append_evidence(run_state, decision.completion_evidence)
    if decision.status == "done":
        run_state.current_stage = "complete"
    elif decision.status == "blocked":
        run_state.current_stage = "blocked"


def _apply_visual_state(run_state: GuiRunState, visual_state: GuiPerceptionState) -> None:
    visual_state = _sanitize_perception_state(run_state, visual_state)
    run_state.last_visual_state = visual_state.to_dict()
    run_state.last_visual_evidence = visual_state.evidence
    run_state.perception_stage = visual_state.stage or "observe"
    run_state.perception_confidence = visual_state.confidence
    _update_perception_stability(run_state, visual_state)

    if visual_state.evidence:
        _append_evidence(run_state, f"Visual check: {visual_state.evidence}")

    if visual_state.ui_summary:
        _append_evidence(run_state, f"Perception summary: {visual_state.ui_summary}")

    if visual_state.blocked:
        run_state.current_stage = "blocked"

    if run_state.goal_kind == "open_chat":
        _apply_open_chat_visual_state(run_state, visual_state)
        _refresh_done_gate(run_state)
        return

    if run_state.goal_kind in {"open_calendar", "create_calendar_event"}:
        _apply_calendar_visual_state(run_state, visual_state)
        _refresh_done_gate(run_state)
        return

    if run_state.goal_kind == "clear_composer":
        if visual_state.composer_empty:
            run_state.current_stage = "verify"
            _append_evidence(run_state, "Current screenshot shows the composer is empty.")
        elif visual_state.composer_text:
            run_state.current_stage = "compose"
            _append_evidence(run_state, f"Current screenshot still shows draft text: {visual_state.composer_text!r}")
        _refresh_done_gate(run_state)
        return

    if run_state.goal_kind not in {"send_message", "compose_message"} or not run_state.target_message:
        _refresh_done_gate(run_state)
        return

    _message_apply_visual_state(
        run_state,
        visual_state,
        normalize_text=_normalize_text,
        append_evidence=_append_evidence,
        refresh_done_gate=_refresh_done_gate,
        initialize_send_message_baseline_cb=_initialize_send_message_baseline,
        initialize_late_send_message_baseline_cb=_initialize_late_send_message_baseline,
    )


def _apply_execution_state(run_state: GuiRunState, decision: GuiDecision, execution: Any) -> None:
    action = decision.action
    if action is None or not getattr(execution, "ok", False):
        _refresh_done_gate(run_state)
        return

    if run_state.goal_kind in {"send_message", "compose_message"}:
        _message_apply_execution_state(
            run_state,
            decision,
            execution,
            is_select_all_action=_is_select_all_action,
            is_submit_action=_is_submit_action,
            normalize_text=_normalize_text,
            append_evidence=_append_evidence,
            refresh_done_gate=_refresh_done_gate,
        )
        return
    if run_state.goal_kind == "clear_composer":
        if action.type != "wait":
            run_state.clear_actions += 1
        if _is_submit_action(action):
            run_state.submit_actions += 1
            run_state.current_stage = "submit"
            _append_evidence(run_state, f"Unexpected submit action during clear-composer run: {action.type}")
        elif action.type == "click":
            run_state.current_stage = "compose"
            _append_evidence(run_state, "Focused the message composer before clearing the draft.")
        elif _is_select_all_action(action):
            run_state.current_stage = "compose"
            _append_evidence(run_state, "Selected all visible draft text in the composer.")
        elif _is_delete_text_action(action):
            run_state.current_stage = "compose"
            _append_evidence(run_state, "Deleted selected or focused draft text in the composer.")
        else:
            run_state.current_stage = decision.stage or "compose"
    elif run_state.goal_kind == "send_emoji":
        if action.target == "feishu composer smiley emoji button (heuristic)":
            run_state.current_stage = "compose"
            _append_evidence(run_state, "Opened the Feishu emoji picker during this run.")
        elif action.target == "feishu emoji picker frequent emoji tile (heuristic)":
            run_state.compose_actions += 1
            run_state.emoji_composed = True
            run_state.current_stage = "compose"
            _append_evidence(run_state, "Selected an emoji into the composer during this run.")
        elif _is_submit_action(action):
            run_state.submit_actions += 1
            run_state.current_stage = "submit"
            _append_evidence(run_state, f"Executed emoji submit action during this run: {action.type}")
        else:
            run_state.current_stage = decision.stage or "navigate"
    elif run_state.goal_kind in {"open_chat", "open_calendar", "create_calendar_event"}:
        if action.type != "wait":
            run_state.navigation_actions += 1
        if run_state.goal_kind == "create_calendar_event" and _is_calendar_slot_action(action):
            run_state.calendar_slot_action_count += 1
            run_state.current_stage = "compose"
            _append_evidence(run_state, "Clicked a calendar time slot while creating a new event.")
        elif run_state.goal_kind == "create_calendar_event" and action.type == "type" and action.text:
            run_state.current_stage = "compose"
            if run_state.calendar_event_title_target and _normalize_text(action.text) == _normalize_text(run_state.calendar_event_title_target):
                _append_evidence(run_state, f"Typed the target calendar event title during this run: {action.text!r}")
            else:
                _append_evidence(run_state, f"Typed calendar editor text during this run: {action.text!r}")
        elif run_state.goal_kind == "create_calendar_event" and _is_calendar_save_action(action):
            run_state.calendar_save_actions += 1
            run_state.current_stage = "submit"
            _append_evidence(run_state, "Clicked Save in the calendar event editor during this run.")
        else:
            run_state.current_stage = decision.stage or "navigate"
    else:
        run_state.current_stage = decision.stage or "in_progress"

    _refresh_done_gate(run_state)


def _done_gate_error(decision: GuiDecision, run_state: GuiRunState) -> str | None:
    if decision.status != "done":
        return None
    if run_state.goal_kind not in {"send_message", "compose_message", "clear_composer", "send_emoji", "open_chat", "open_calendar", "create_calendar_event"}:
        return None
    if run_state.done_gate_ready:
        return None
    return run_state.done_gate_reason or "This run does not yet contain enough completion evidence."


def _blocked_gate_error(decision: GuiDecision, run_state: GuiRunState) -> str | None:
    if decision.status != "blocked":
        return None
    if run_state.goal_kind != "create_calendar_event":
        return None
    if run_state.calendar_slot_action_count > 0 or run_state.calendar_save_actions > 0:
        return None

    visual_state = run_state.last_visual_state or {}
    visible_title = _normalize_text(str(visual_state.get("calendar_saved_event_title", "")).strip())
    target_title = _normalize_text(run_state.calendar_event_title_target)
    matching_visible = run_state.calendar_preexisting_matching_event_visible or (
        bool(visual_state.get("calendar_saved_event_visible", False))
        and (not target_title or visible_title == target_title)
    )
    if not matching_visible:
        return None

    return (
        "A pre-existing matching calendar event tile does not count as work completed in this run. "
        "Do not block yet; continue with slot click, title entry, Save, and post-save verification."
    )


def _submit_gate_error(decision: GuiDecision, run_state: GuiRunState) -> str | None:
    return _message_submit_gate_error(
        decision,
        run_state,
        is_submit_action=_is_submit_action,
    )


def _refresh_done_gate(run_state: GuiRunState) -> None:
    if run_state.goal_kind == "clear_composer":
        if run_state.submit_actions > 0:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This clear-draft run executed a send/submit action, which violates the goal."
            return
        visual_state = run_state.last_visual_state or {}
        if not bool(visual_state.get("composer_empty", False)):
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The composer is not visually empty yet."
            return
        run_state.done_gate_ready = True
        run_state.done_gate_reason = "The composer is visually empty and no send/submit action occurred."
        return

    if run_state.goal_kind == "compose_message":
        if _message_refresh_done_gate(run_state):
            return

    if run_state.goal_kind == "send_message":
        if _message_refresh_done_gate(run_state):
            return

    if run_state.goal_kind == "send_emoji":
        if run_state.submit_actions <= 0:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run has not executed the emoji send action yet."
            return
        if not run_state.emoji_composed:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run has not recorded emoji composition before submit."
            return
        run_state.done_gate_ready = True
        run_state.done_gate_reason = "This run recorded emoji composition and submit."
        return

    if run_state.goal_kind == "open_chat":
        if _chat_refresh_done_gate(run_state):
            return

    if run_state.goal_kind in {"open_calendar", "create_calendar_event"}:
        if _calendar_refresh_done_gate(run_state):
            return

    run_state.done_gate_ready = True
    run_state.done_gate_reason = "Generic goal does not require a send-proof gate."


def _summarize_run_state(run_state: GuiRunState) -> str:
    typed_preview = ", ".join(repr(text) for text in run_state.typed_texts[-2:]) or "(none)"
    evidence_preview = "; ".join(run_state.completion_evidence[-3:]) or "(none)"
    workflow_preview = " -> ".join(run_state.workflow_steps) or "(planner has not emitted workflow steps yet)"
    return "\n".join(
        [
            f"- Goal kind: {run_state.goal_kind}",
            f"- Target message: {run_state.target_message or '(none)'}",
            f"- Pending message text: {run_state.pending_message_text or '(none)'}",
            f"- Target label: {run_state.target_label or '(none)'}",
            f"- Calendar event title target: {run_state.calendar_event_title_target or '(none)'}",
            f"- Calendar target time hint: {run_state.calendar_target_time_hint or '(none)'}",
            f"- Baseline composer text: {run_state.baseline_composer_text or '(empty)'}",
            f"- Baseline composer dirty: {run_state.baseline_composer_nonempty}",
            f"- Baseline composer exact match: {run_state.baseline_composer_exact_match}",
            f"- Current stage: {run_state.current_stage}",
            f"- Planner stage: {run_state.planner_stage}",
            f"- Perception stage: {run_state.perception_stage}",
            f"- Compose actions this run: {run_state.compose_actions}",
            f"- Submit actions this run: {run_state.submit_actions}",
            f"- Clear actions this run: {run_state.clear_actions}",
            f"- Perception stable: {run_state.perception_stable}",
            f"- Perception repeat count: {run_state.perception_repeat_count}/{run_state.perception_stable_after}",
            f"- Perception confidence: {run_state.perception_confidence:.2f}",
            f"- Target message typed this run: {run_state.target_message_typed}",
            f"- Target message visually verified: {run_state.target_message_visually_verified}",
            f"- Emoji composed this run: {run_state.emoji_composed}",
            f"- Send visually confirmed: {run_state.send_visually_confirmed}",
            f"- Composer reset required: {run_state.composer_reset_required}",
            f"- Composer reset started: {run_state.composer_reset_started}",
            f"- Composer reset completed: {run_state.composer_reset_satisfied}",
            f"- Navigation actions this run: {run_state.navigation_actions}",
            f"- Open chat verified: {run_state.chat_target_open_verified}",
            f"- Calendar visible verified: {run_state.calendar_visible_verified}",
            f"- Calendar today highlighted verified: {run_state.calendar_today_highlighted_verified}",
            f"- Calendar today label: {run_state.calendar_today_label or '(unknown)'}",
            f"- Calendar event editor verified: {run_state.calendar_event_editor_verified}",
            f"- Calendar slot actions this run: {run_state.calendar_slot_action_count}",
            f"- Calendar event title typed verified: {run_state.calendar_event_title_typed_verified}",
            f"- Calendar event title current: {run_state.calendar_event_title_current or '(none)'}",
            f"- Calendar time range verified: {run_state.calendar_time_range_verified}",
            f"- Calendar save actions this run: {run_state.calendar_save_actions}",
            f"- Calendar event saved verified: {run_state.calendar_event_saved_verified}",
            f"- Calendar matching event already visible before create: {run_state.calendar_preexisting_matching_event_visible}",
            f"- Typed texts this run: {typed_preview}",
            f"- Planner workflow: {workflow_preview}",
            f"- Last visual check: {_describe_visual_state(run_state)}",
            f"- Completion gate: {'ready' if run_state.done_gate_ready else 'not ready'}",
            f"- Completion gate reason: {run_state.done_gate_reason}",
            f"- Evidence: {evidence_preview}",
            "- Old visible messages are baseline only. They do not prove success for this run.",
        ]
    )


def _append_evidence(run_state: GuiRunState, evidence: str) -> None:
    evidence = evidence.strip()
    if not evidence:
        return
    if evidence not in run_state.completion_evidence:
        run_state.completion_evidence.append(evidence)


def _sanitize_perception_state(run_state: GuiRunState, visual_state: GuiPerceptionState) -> GuiPerceptionState:
    visual_state.primary_view = _normalize_text(visual_state.primary_view)
    visual_state.selected_sidebar_item = _normalize_text(visual_state.selected_sidebar_item)
    composer_text = _normalize_text(visual_state.composer_text)
    placeholder_text = _normalize_text(visual_state.composer_placeholder)
    latest_visible_message = _normalize_text(visual_state.latest_visible_message)
    target_message = _normalize_text(run_state.pending_message_text or run_state.target_message)
    visual_state.calendar_today_label = _normalize_text(visual_state.calendar_today_label)
    visual_state.calendar_event_editor_title_text = _normalize_text(visual_state.calendar_event_editor_title_text)
    visual_state.calendar_event_time_range = _normalize_text(visual_state.calendar_event_time_range)
    visual_state.calendar_saved_event_title = _normalize_text(visual_state.calendar_saved_event_title)

    if not visual_state.calendar_event_editor_visible:
        visual_state.calendar_event_editor_title_text = ""
        visual_state.calendar_event_time_range = ""
        visual_state.calendar_save_button_visible = False

    if not visual_state.calendar_saved_event_visible:
        visual_state.calendar_saved_event_title = ""

    if not composer_text:
        visual_state.composer_text = ""
        visual_state.composer_empty = True
        visual_state.composer_exact_match = False
    else:
        visual_state.composer_text = composer_text
        visual_state.composer_empty = False
        visual_state.composer_exact_match = bool(target_message) and visual_state.composer_visible and composer_text == target_message

    if placeholder_text and not composer_text:
        visual_state.composer_placeholder = placeholder_text
        visual_state.composer_empty = True
        visual_state.composer_exact_match = False

    visual_state.latest_visible_message = latest_visible_message
    if target_message:
        visual_state.sent_message_exact_match = bool(visual_state.sent_message_visible) and bool(latest_visible_message) and latest_visible_message == target_message
    elif not latest_visible_message:
        visual_state.sent_message_exact_match = False

    if visual_state.composer_exact_match and visual_state.composer_empty:
        visual_state.composer_exact_match = False

    return visual_state


def _update_perception_stability(run_state: GuiRunState, visual_state: GuiPerceptionState) -> None:
    signature = visual_state.signature(run_state.target_message)
    if signature == run_state.perception_signature:
        run_state.perception_repeat_count += 1
    else:
        run_state.perception_signature = signature
        run_state.perception_repeat_count = 1
    run_state.perception_stable = run_state.perception_repeat_count >= run_state.perception_stable_after


def _describe_visual_state(run_state: GuiRunState) -> str:
    visual_state = run_state.last_visual_state or {}
    if not visual_state:
        return "no visual verification yet"
    if (
        run_state.goal_kind == "create_calendar_event"
        and run_state.calendar_preexisting_matching_event_visible
        and run_state.calendar_slot_action_count <= 0
        and run_state.calendar_save_actions <= 0
        and bool(visual_state.get("calendar_saved_event_visible", False))
    ):
        title = str(visual_state.get("calendar_saved_event_title", "")).strip()
        return f"matching calendar event already visible before this run{f' for {title!r}' if title else ''}"
    if bool(visual_state.get("calendar_saved_event_visible", False)):
        title = str(visual_state.get("calendar_saved_event_title", "")).strip()
        return f"calendar saved event visible{f' for {title!r}' if title else ''}"
    if bool(visual_state.get("calendar_event_editor_visible", False)):
        title = str(visual_state.get("calendar_event_editor_title_text", "")).strip()
        return f"calendar event editor visible{f' with title {title!r}' if title else ''}"
    calendar_state = _calendar_describe_visual_state(run_state)
    if calendar_state:
        return calendar_state
    message_state = _message_describe_visual_state(run_state, normalize_text=_normalize_text)
    if message_state:
        return message_state
    return visual_state.get("evidence", "visual state captured")


def _is_submit_action(action: Any) -> bool:
    action_type = getattr(action, "type", "")
    target = str(getattr(action, "target", "")).lower()

    if action_type == "hotkey":
        keys = [str(key).lower() for key in (getattr(action, "keys", None) or [])]
        if keys == ["enter"]:
            return True
        if keys in (["command", "enter"], ["ctrl", "enter"]):
            return True

    if action_type == "click" and _target_looks_like_send_control(target):
        return True

    return False


def _target_looks_like_send_control(target: str) -> bool:
    explicit_send_control = any(
        keyword in target
        for keyword in (
            "send button",
            "send icon",
            "submit button",
            "blue send",
            "发送按钮",
            "发送图标",
            "发送键",
            "蓝色发送",
        )
    )
    if explicit_send_control:
        return True

    if any(
        keyword in target
        for keyword in (
            "composer",
            "input",
            "message box",
            "message composer",
            "placeholder",
            "输入框",
            "消息输入",
            "发送给",
        )
    ):
        return False
    return any(keyword in target for keyword in ("send", "submit"))


def _is_select_all_action(action: Any) -> bool:
    if getattr(action, "type", "") != "hotkey":
        return False
    keys = [str(key).lower() for key in (getattr(action, "keys", None) or [])]
    return keys in (["command", "a"], ["ctrl", "a"])


def _is_delete_text_action(action: Any) -> bool:
    if getattr(action, "type", "") != "hotkey":
        return False
    keys = [str(key).lower() for key in (getattr(action, "keys", None) or [])]
    return keys in (["backspace"], ["delete"])


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _initialize_send_message_baseline(run_state: GuiRunState, visual_state: GuiPerceptionState) -> None:
    _message_initialize_send_message_baseline(
        run_state,
        visual_state,
        append_evidence=_append_evidence,
    )


def _initialize_late_send_message_baseline(run_state: GuiRunState, visual_state: GuiPerceptionState) -> None:
    _message_initialize_late_send_message_baseline(run_state, visual_state)


def _apply_open_chat_visual_state(run_state: GuiRunState, visual_state: GuiPerceptionState) -> None:
    _chat_apply_open_chat_visual_state(
        run_state,
        visual_state,
        normalize_text=_normalize_text,
        append_evidence=_append_evidence,
    )


def _apply_calendar_visual_state(run_state: GuiRunState, visual_state: GuiPerceptionState) -> None:
    _calendar_apply_visual_state(
        run_state,
        visual_state,
        normalize_text=_normalize_text,
        append_evidence=_append_evidence,
        looks_like_calendar_view=_looks_like_calendar_view,
    )


def _apply_workflow_plan(run_state: GuiRunState, workflow_steps: list[str], active_step_index: int | None) -> None:
    normalized_steps = _normalize_workflow_steps(workflow_steps)
    if normalized_steps:
        run_state.workflow_steps = normalized_steps
    if not run_state.workflow_steps:
        return

    if active_step_index is None or active_step_index < 0 or active_step_index >= len(run_state.workflow_steps):
        active_step_index = min(_infer_active_workflow_index(run_state), len(run_state.workflow_steps) - 1)
    run_state.workflow_active_step_index = active_step_index


def _normalize_workflow_steps(workflow_steps: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for step in workflow_steps:
        text = str(step).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized[:6]


def _infer_active_workflow_index(run_state: GuiRunState) -> int:
    if run_state.current_stage in {"baseline_captured", "observe"}:
        return 0
    if run_state.composer_reset_required and not run_state.composer_reset_satisfied:
        return 1 if len(run_state.workflow_steps) > 1 else 0
    if run_state.current_stage == "compose":
        return min(2, max(len(run_state.workflow_steps) - 1, 0))
    if run_state.current_stage == "submit":
        return min(3, max(len(run_state.workflow_steps) - 1, 0))
    if run_state.current_stage in {"verify", "complete"}:
        return max(len(run_state.workflow_steps) - 1, 0)
    return 0


def _serialize_workflow_steps(
    run_state: GuiRunState,
    *,
    decision_status: str | None = None,
    success: bool | None = None,
) -> list[dict[str, str]]:
    titles = run_state.workflow_steps or [_default_workflow_title(run_state)]
    if not titles:
        return []

    active_index = run_state.workflow_active_step_index
    if active_index is None:
        active_index = min(_infer_active_workflow_index(run_state), len(titles) - 1)

    items: list[dict[str, str]] = []
    for index, title in enumerate(titles):
        if success is True or decision_status == "done":
            status = "done"
        elif success is False or decision_status == "blocked":
            if index < active_index:
                status = "done"
            elif index == active_index:
                status = "blocked"
            else:
                status = "pending"
        elif index < active_index:
            status = "done"
        elif index == active_index:
            status = "active"
        else:
            status = "pending"
        items.append({"title": title, "status": status})
    return items


def _default_workflow_title(run_state: GuiRunState) -> str:
    if run_state.goal_kind == "send_message":
        return "Observe current chat"
    if run_state.goal_kind == "open_chat":
        return "Open target conversation"
    if run_state.goal_kind == "open_calendar":
        return "Open Calendar module"
    if run_state.goal_kind == "create_calendar_event":
        return "Open Calendar and create event"
    return "Observe target window"


def _maybe_apply_feishu_emoji_heuristic(
    goal: str,
    observation: ScreenshotArtifact,
    history: list[dict[str, Any]],
    step_index: int,
    app_name: str,
) -> GuiDecision | None:
    if app_name.lower() != "feishu":
        return None
    if not _looks_like_emoji_goal(goal):
        return None

    open_button_x = int(round(observation.width * 0.79))
    open_button_y = int(round(observation.height * 0.915))
    frequent_emoji_x = int(round(observation.width * 0.626))
    frequent_emoji_y = int(round(observation.height * 0.318))

    previous_targets = [(item.get("action") or {}).get("target", "") for item in history]
    previous_attempts = [target for target in previous_targets if "smiley" in target.lower()]
    used_near_heuristic = any(
        abs(((item.get("action") or {}).get("x") or -9999) - open_button_x) <= 80 and
        abs(((item.get("action") or {}).get("y") or -9999) - open_button_y) <= 80
        for item in history
    )

    if step_index == 1:
        return GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "Feishu chat composer is visible and the goal is to open the emoji picker.",
                "progress_assessment": "Using the Feishu composer emoji-button heuristic for the first click.",
                "previous_step_ok": True,
                "success_criteria": "The emoji picker opens above the composer.",
                "completion_evidence": "No new emoji has been sent yet in this run.",
                "action": {
                    "type": "click",
                    "target": "feishu composer smiley emoji button (heuristic)",
                    "x": open_button_x,
                    "y": open_button_y,
                },
            }
        )

    if previous_targets and previous_targets[-1] == "feishu composer smiley emoji button (heuristic)":
        return GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The Feishu emoji picker should now be open.",
                "progress_assessment": "Using the Feishu emoji-picker heuristic to choose a visible frequently used emoji tile.",
                "previous_step_ok": True,
                "success_criteria": "A visible emoji is inserted into the message composer.",
                "completion_evidence": "The run has opened the emoji picker but has not submitted anything yet.",
                "action": {
                    "type": "click",
                    "target": "feishu emoji picker frequent emoji tile (heuristic)",
                    "x": frequent_emoji_x,
                    "y": frequent_emoji_y,
                },
            }
        )

    if previous_targets and previous_targets[-1] == "feishu emoji picker frequent emoji tile (heuristic)":
        return GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "A single emoji should now be present in the composer.",
                "progress_assessment": "Submitting the composed emoji with Enter.",
                "previous_step_ok": True,
                "success_criteria": "A new chat message containing the emoji is sent.",
                "completion_evidence": "This run already composed an emoji and is now submitting it.",
                "action": {
                    "type": "hotkey",
                    "target": "feishu submit composed emoji (heuristic)",
                    "keys": ["enter"],
                },
            }
        )

    if previous_attempts and not used_near_heuristic:
        return GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "Repeated model clicks did not open the emoji picker.",
                "progress_assessment": "Switching to the Feishu composer emoji-button heuristic because previous smiley clicks were off-target.",
                "previous_step_ok": True,
                "success_criteria": "The emoji picker opens above the composer.",
                "completion_evidence": "Prior clicks did not create a valid send event in this run.",
                "action": {
                    "type": "click",
                    "target": "feishu composer smiley emoji button (heuristic)",
                    "x": open_button_x,
                    "y": open_button_y,
                },
            }
        )

    return None


def _looks_like_chat_window_view(primary_view: str) -> bool:
    return _chat_looks_like_window_view(primary_view, normalize_text=_normalize_text)


def _looks_like_calendar_view(primary_view: str) -> bool:
    view = _normalize_text(primary_view).lower()
    return "calendar" in view


def _is_calendar_slot_action(action: Any) -> bool:
    return _calendar_is_slot_action(action, normalize_text=_normalize_text)


def _is_calendar_save_action(action: Any) -> bool:
    return _calendar_is_save_action(action, normalize_text=_normalize_text)


def _image_to_data_url(path: Path) -> str:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    try:
        with Image.open(path) as image:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=78, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"


def _summarize_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return "(no previous steps)"
    lines = []
    for item in history[-6:]:
        action = item.get("action") or {}
        screen_action = item.get("screen_action") or {}
        execution = item.get("execution") or {}
        state_after = item.get("state_after_action") or {}
        action_bits = [f"action={action.get('type')}"]
        if action.get("target"):
            action_bits.append(f"target={action.get('target')}")
        if action.get("x") is not None and action.get("y") is not None:
            action_bits.append(f"image_xy=({action.get('x')},{action.get('y')})")
        if screen_action.get("x") is not None and screen_action.get("y") is not None:
            action_bits.append(f"screen_xy=({screen_action.get('x')},{screen_action.get('y')})")
        if action.get("text"):
            action_bits.append(f"text={action.get('text')!r}")
        if action.get("keys"):
            action_bits.append(f"keys={action.get('keys')}")
        if state_after.get("current_stage"):
            action_bits.append(f"run_stage={state_after.get('current_stage')}")
        if state_after.get("done_gate_ready") is not None:
            action_bits.append(f"done_gate_ready={state_after.get('done_gate_ready')}")
        action_bits.append(f"result={execution.get('detail', '')}")
        lines.append(
            f"Step {item['step_index']}: " + " ".join(action_bits)
        )
    return "\n".join(lines)


def _env_flag(names: tuple[str, ...], default: bool) -> bool:
    value = _first_nonempty_env(names, "")
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _build_gui_client(default_client: OpenAI) -> OpenAI:
    api_key = _first_nonempty_env(("GUI_VLM_API_KEY", "VLM_API_KEY", "CUA_API_KEY"), "")
    api_base = _first_nonempty_env(("GUI_VLM_API_BASE", "VLM_API_BASE", "CUA_API_BASE"), "").rstrip("/")
    if api_key:
        base_url = api_base or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
        return OpenAI(api_key=api_key, base_url=base_url)
    return default_client


def _first_nonempty_env(names: tuple[str, ...], default: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _decision_bounds_error(decision: GuiDecision, observation: ScreenshotArtifact) -> str | None:
    action = decision.action
    if action is None:
        return None

    max_x = observation.width - 1
    max_y = observation.height - 1

    if action.type in {"click", "double_click", "right_click"}:
        if not _in_bounds(action.x, action.y, max_x, max_y):
            return f"{action.type} coordinates ({action.x}, {action.y}) are outside the screenshot"
    elif action.type == "drag":
        if not _in_bounds(action.x, action.y, max_x, max_y):
            return f"drag start ({action.x}, {action.y}) is outside the screenshot"
        if not _in_bounds(action.end_x, action.end_y, max_x, max_y):
            return f"drag end ({action.end_x}, {action.end_y}) is outside the screenshot"
    elif action.type == "scroll":
        if action.x is not None and action.y is not None and not _in_bounds(action.x, action.y, max_x, max_y):
            return f"scroll anchor ({action.x}, {action.y}) is outside the screenshot"
    return None


def _in_bounds(x: int | None, y: int | None, max_x: int, max_y: int) -> bool:
    if x is None or y is None:
        return False
    return 0 <= x <= max_x and 0 <= y <= max_y
