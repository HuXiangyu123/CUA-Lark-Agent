"""Message-composer flow helpers for GUI runs."""

from __future__ import annotations

import sys
from typing import Any, Callable


def maybe_apply_message_compose_heuristic(
    observation: Any,
    history: list[dict[str, Any]],
    run_state: Any,
    *,
    decision_from_dict: Callable[[dict[str, Any]], Any],
) -> Any | None:
    if run_state.goal_kind not in {"send_message", "compose_message"}:
        return None

    pending_text = run_state.pending_message_text.strip()
    if not pending_text:
        return None
    if run_state.submit_actions > 0:
        return None

    visual_state = run_state.last_visual_state or {}
    composer_visible = bool(visual_state.get("composer_visible", False))
    composer_empty = bool(visual_state.get("composer_empty", False))
    composer_exact_match = bool(visual_state.get("composer_exact_match", False))
    composer_text = str(visual_state.get("composer_text", "")).strip()
    if not composer_visible:
        return None

    recent_actions = [
        ((item.get("action") or {}).get("target") or "")
        for item in history
        if isinstance(item, dict)
    ]
    focus_target = "message composer focus"
    select_target = "message composer select all"
    delete_target = "message composer delete selection"
    focus_count = recent_actions.count(focus_target)
    select_count = recent_actions.count(select_target)
    delete_count = recent_actions.count(delete_target)

    needs_reset = (run_state.composer_reset_required and not run_state.composer_reset_satisfied) or (
        composer_text and not composer_exact_match
    )
    if not needs_reset and composer_exact_match:
        return None

    if focus_count == 0:
        composer_x = max(24, min(observation.width - 180, int(observation.width * 0.08)))
        composer_y = max(1, observation.height - 45)
        return decision_from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The composer needs focus before clearing or replacing text.",
                "progress_assessment": "Focusing the composer ensures keyboard shortcuts apply to the input box.",
                "previous_step_ok": True,
                "success_criteria": "The message composer becomes focused.",
                "workflow_steps": ["Focus composer", "Select all existing text", "Clear stale text", "Type pending message", "Submit send action"],
                "active_step_index": 0,
                "action": {
                    "type": "click",
                    "target": focus_target,
                    "x": composer_x,
                    "y": composer_y,
                },
            }
        )

    if needs_reset and select_count == 0:
        modifier = "command" if sys.platform == "darwin" else "ctrl"
        return decision_from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The composer contains existing text that must not be submitted as-is.",
                "progress_assessment": "Selecting all existing text prepares a safe reset before sending.",
                "previous_step_ok": True,
                "success_criteria": "All existing composer text becomes selected.",
                "workflow_steps": ["Focus composer", "Select all existing text", "Clear stale text", "Type pending message", "Submit send action"],
                "active_step_index": 1,
                "action": {
                    "type": "hotkey",
                    "target": select_target,
                    "keys": [modifier, "a"],
                },
            }
        )

    if needs_reset and not composer_empty and delete_count == 0:
        return decision_from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The composer still appears non-empty and should be cleared before typing.",
                "progress_assessment": "Clearing stale text avoids mixed or duplicated drafts.",
                "previous_step_ok": True,
                "success_criteria": "The composer becomes empty.",
                "workflow_steps": ["Focus composer", "Select all existing text", "Clear stale text", "Type pending message", "Submit send action"],
                "active_step_index": 2,
                "action": {
                    "type": "hotkey",
                    "target": delete_target,
                    "keys": ["backspace"],
                },
            }
        )

    if composer_empty and not composer_exact_match:
        return decision_from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "The composer is empty and ready for the pending message.",
                "progress_assessment": "Typing the pending message prepares the exact send payload.",
                "previous_step_ok": True,
                "success_criteria": "The composer shows the full pending message text.",
                "workflow_steps": ["Focus composer", "Select all existing text", "Clear stale text", "Type pending message", "Submit send action"],
                "active_step_index": 3,
                "action": {
                    "type": "type",
                    "target": "message composer type pending text",
                    "text": pending_text,
                },
            }
        )

    return None


def initialize_send_message_baseline(run_state: Any, visual_state: Any, *, append_evidence: Callable[[Any, str], None]) -> None:
    run_state.baseline_initialized = True
    run_state.baseline_latest_visible_message = visual_state.latest_visible_message
    run_state.baseline_sent_message_exact_match = visual_state.sent_message_exact_match
    run_state.baseline_composer_text = visual_state.composer_text
    run_state.baseline_composer_nonempty = bool(visual_state.composer_text)
    run_state.baseline_composer_exact_match = visual_state.composer_exact_match
    run_state.composer_reset_required = run_state.baseline_composer_nonempty

    if not run_state.baseline_composer_nonempty:
        return

    if run_state.baseline_composer_exact_match:
        append_evidence(
            run_state,
            "Baseline composer already contains the exact target text. Treating it as a stale draft that must be cleared or replaced in this run.",
        )
        return

    append_evidence(
        run_state,
        f"Baseline composer already contains stale draft text: {run_state.baseline_composer_text!r}. It must be cleared or replaced before submit.",
    )


def initialize_late_send_message_baseline(run_state: Any, visual_state: Any) -> None:
    run_state.baseline_initialized = True
    run_state.baseline_latest_visible_message = visual_state.latest_visible_message
    run_state.baseline_sent_message_exact_match = visual_state.sent_message_exact_match
    run_state.baseline_composer_text = ""
    run_state.baseline_composer_nonempty = False
    run_state.baseline_composer_exact_match = False
    run_state.composer_reset_required = False


def apply_message_visual_state(
    run_state: Any,
    visual_state: Any,
    *,
    normalize_text: Callable[[str], str],
    append_evidence: Callable[[Any, str], None],
    refresh_done_gate: Callable[[Any], None],
    initialize_send_message_baseline_cb: Callable[[Any, Any], None],
    initialize_late_send_message_baseline_cb: Callable[[Any, Any], None],
) -> None:
    if not run_state.baseline_initialized:
        if run_state.compose_actions <= 0 and run_state.submit_actions <= 0:
            initialize_send_message_baseline_cb(run_state, visual_state)
        else:
            initialize_late_send_message_baseline_cb(run_state, visual_state)

    if run_state.composer_reset_required and not run_state.composer_reset_satisfied:
        if visual_state.composer_empty:
            run_state.composer_reset_satisfied = True
            append_evidence(run_state, "The stale baseline draft was cleared from the composer during this run.")
        elif run_state.composer_reset_started and run_state.compose_actions > 0 and visual_state.composer_exact_match:
            run_state.composer_reset_satisfied = True
            append_evidence(run_state, "The stale baseline draft was replaced with a freshly typed exact target message during this run.")

    if visual_state.composer_exact_match:
        if run_state.composer_reset_required and not run_state.composer_reset_satisfied:
            append_evidence(
                run_state,
                "The composer currently shows the target text, but it still counts as a stale baseline draft until this run clears or replaces it.",
            )
        else:
            run_state.target_message_visually_verified = True
            append_evidence(run_state, "Current screenshot shows the exact target text in the composer.")
            if run_state.compose_actions <= 0:
                append_evidence(run_state, "The exact target text was already present in the composer before any new type action in this run.")
    elif visual_state.composer_text:
        if normalize_text(visual_state.composer_text) != normalize_text(run_state.target_message):
            append_evidence(
                run_state,
                f"Current screenshot shows composer text mismatch: {visual_state.composer_text!r}",
            )
    elif visual_state.composer_empty:
        append_evidence(run_state, "Current screenshot shows an empty composer.")

    submitted_target_this_run = (
        run_state.submit_actions > 0
        and (run_state.target_message_typed or run_state.target_message_visually_verified)
    )
    visible_new_or_typed_target = (
        visual_state.sent_message_exact_match
        and (
            run_state.target_message_typed
            or normalize_text(visual_state.latest_visible_message) != normalize_text(run_state.baseline_latest_visible_message)
        )
    )
    if submitted_target_this_run and visible_new_or_typed_target:
        run_state.send_visually_confirmed = True
        run_state.current_stage = "verify"
        append_evidence(run_state, "Current screenshot shows the exact target message after this run submitted it.")
    elif submitted_target_this_run and visual_state.composer_empty:
        run_state.send_visually_confirmed = True
        run_state.current_stage = "verify"
        append_evidence(run_state, "Composer cleared after this run typed and submitted the exact target text.")
    elif visual_state.sent_message_exact_match and run_state.submit_actions <= 0:
        append_evidence(run_state, "The target message is visible in baseline chat history, but this run has not submitted anything yet.")

    refresh_done_gate(run_state)


def apply_message_execution_state(
    run_state: Any,
    decision: Any,
    execution: Any,
    *,
    is_select_all_action: Callable[[Any], bool],
    is_submit_action: Callable[[Any], bool],
    normalize_text: Callable[[str], str],
    append_evidence: Callable[[Any, str], None],
    refresh_done_gate: Callable[[Any], None],
) -> None:
    action = decision.action
    if action is None or not getattr(execution, "ok", False):
        refresh_done_gate(run_state)
        return

    if is_select_all_action(action) and run_state.composer_reset_required and not run_state.composer_reset_satisfied:
        run_state.composer_reset_started = True
        run_state.current_stage = "compose"
        append_evidence(run_state, "Selected the existing baseline draft so it can be cleared or replaced.")
    elif action.type == "type" and action.text:
        run_state.compose_actions += 1
        run_state.current_stage = "compose"
        run_state.typed_texts.append(action.text)
        pending_text = run_state.pending_message_text or run_state.target_message
        if pending_text and normalize_text(action.text) == normalize_text(pending_text):
            run_state.target_message_typed = True
            append_evidence(run_state, f"Typed target message during this run: {action.text!r}")
        else:
            append_evidence(run_state, f"Typed message during this run: {action.text!r}")
    elif is_submit_action(action):
        run_state.submit_actions += 1
        run_state.current_stage = "submit"
        append_evidence(run_state, f"Executed submit action during this run: {action.type}")
    else:
        run_state.current_stage = decision.stage or "navigate"

    refresh_done_gate(run_state)


def submit_gate_error(
    decision: Any,
    run_state: Any,
    *,
    is_submit_action: Callable[[Any], bool],
) -> str | None:
    action = decision.action
    if decision.status != "continue" or action is None:
        return None
    if not is_submit_action(action):
        return None
    if run_state.goal_kind == "clear_composer":
        return "The goal is to clear an unsent draft; do not click send or submit."
    if run_state.goal_kind == "compose_message":
        return "The goal explicitly says to leave the message as an unsent draft; do not click send or submit."
    intended_text = run_state.pending_message_text or run_state.target_message
    if run_state.goal_kind != "send_message" or not intended_text:
        return None
    if run_state.composer_reset_required and not run_state.composer_reset_satisfied:
        baseline_text = run_state.baseline_composer_text or "stale draft text"
        return (
            "The baseline composer already contained stale text "
            f"({baseline_text!r}). Clear or replace that draft in this run before submitting."
        )
    visual_state = run_state.last_visual_state or {}
    composer_text = str(visual_state.get("composer_text", "")).strip()
    composer_exact_match = bool(visual_state.get("composer_exact_match", False))
    if composer_exact_match:
        if not run_state.perception_stable:
            return "The composer exact-match observation is not stable yet. Re-observe once before submitting."
        return None
    if composer_text:
        return (
            "The composer currently shows mismatched or partial text "
            f"({composer_text!r}) instead of the exact target message {intended_text!r}."
        )
    if run_state.compose_actions <= 0:
        return "This run has not composed or visually verified the target message yet. Do not submit an empty or unrelated composer."
    return (
        "The composer does not visibly contain the exact target message yet. "
        "It is currently empty, placeholder-only, or unreadable."
    )


def refresh_message_done_gate(run_state: Any) -> bool:
    if run_state.goal_kind == "compose_message":
        if run_state.submit_actions > 0:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This draft-only run already executed a send/submit action, which violates the goal."
            return True
        if run_state.compose_actions <= 0 or not run_state.target_message_typed:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run has not typed the exact target draft text yet."
            return True
        if run_state.target_message and not run_state.target_message_visually_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run has not visually verified the exact target draft text in the composer."
            return True
        if not run_state.perception_stable:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The visual completion signal is not stable across observations yet."
            return True
        run_state.done_gate_ready = True
        run_state.done_gate_reason = "This run typed and visually verified the exact draft text without sending it."
        return True

    if run_state.goal_kind == "send_message":
        if run_state.submit_actions <= 0:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run has not executed any send/submit action yet."
            return True
        if (
            run_state.target_message
            and not run_state.target_message_visually_verified
            and not (run_state.submit_actions > 0 and run_state.target_message_typed and run_state.send_visually_confirmed)
        ):
            run_state.done_gate_ready = False
            run_state.done_gate_reason = (
                "This run has not visually verified the exact target text in the composer before submit."
            )
            return True
        if run_state.target_message and not run_state.send_visually_confirmed:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = (
                "This run has not visually confirmed that the exact target message was sent successfully."
            )
            return True
        if not run_state.perception_stable:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The visual completion signal is not stable across observations yet."
            return True
        if not run_state.target_message and run_state.compose_actions <= 0:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run submitted something, but there is no recorded compose step before it."
            return True
        run_state.done_gate_ready = True
        run_state.done_gate_reason = "This run recorded exact text verification, submit, and visual send confirmation."
        return True

    return False


def describe_message_visual_state(run_state: Any, *, normalize_text: Callable[[str], str]) -> str | None:
    visual_state = run_state.last_visual_state or {}
    if not visual_state:
        return None
    primary_view = str(visual_state.get("primary_view", "")).strip().lower()
    if primary_view and ("chat" in primary_view or "conversation" in primary_view):
        title = str(visual_state.get("chat_title", "")).strip()
        return f"chat window visible{f' for {title!r}' if title else ''}"
    composer_text = str(visual_state.get("composer_text", "")).strip()
    intended_text = run_state.pending_message_text or run_state.target_message
    if composer_text and intended_text and normalize_text(composer_text) != normalize_text(intended_text):
        return "composer text mismatches target"
    if bool(visual_state.get("sent_message_exact_match", False)):
        return "exact target message visible in chat"
    if bool(visual_state.get("composer_exact_match", False)):
        return "composer text exactly matches target"
    if bool(visual_state.get("composer_empty", False)):
        return "composer empty"
    return None
