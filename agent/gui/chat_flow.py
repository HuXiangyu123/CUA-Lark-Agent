"""Chat-opening flow helpers for GUI runs."""

from __future__ import annotations

from typing import Any, Callable


def apply_open_chat_visual_state(
    run_state: Any,
    visual_state: Any,
    *,
    normalize_text: Callable[[str], str],
    append_evidence: Callable[[Any, str], None],
) -> None:
    normalized_target = normalize_text(run_state.target_label)
    normalized_chat_title = normalize_text(visual_state.chat_title)
    if normalized_target and normalized_chat_title == normalized_target:
        if visual_state.composer_visible or looks_like_chat_window_view(visual_state.primary_view, normalize_text=normalize_text):
            run_state.chat_target_open_verified = True
            run_state.current_stage = "verify"
            append_evidence(run_state, f"The target conversation {run_state.target_label!r} is visibly open.")
        else:
            append_evidence(
                run_state,
                f"The target chat title {run_state.target_label!r} is visible, but the active conversation window is not confirmed yet.",
            )


def refresh_open_chat_done_gate(run_state: Any) -> bool:
    if run_state.goal_kind != "open_chat":
        return False
    if not run_state.target_label:
        run_state.done_gate_ready = False
        run_state.done_gate_reason = "The target chat title was not extracted from the goal yet."
        return True
    if not run_state.chat_target_open_verified:
        run_state.done_gate_ready = False
        run_state.done_gate_reason = f"The target conversation {run_state.target_label!r} is not visibly open yet."
        return True
    if not run_state.perception_stable:
        run_state.done_gate_ready = False
        run_state.done_gate_reason = "The visual completion signal is not stable across observations yet."
        return True
    run_state.done_gate_ready = True
    run_state.done_gate_reason = f"The target conversation {run_state.target_label!r} is visibly open and stable."
    return True


def looks_like_chat_window_view(primary_view: str, *, normalize_text: Callable[[str], str]) -> bool:
    view = normalize_text(primary_view).lower()
    if not view:
        return False
    return ("chat" in view or "conversation" in view) and "list" not in view
