"""Calendar flow helpers for GUI runs."""

from __future__ import annotations

import re
from typing import Any, Callable


def apply_calendar_visual_state(
    run_state: Any,
    visual_state: Any,
    *,
    normalize_text: Callable[[str], str],
    append_evidence: Callable[[Any, str], None],
    looks_like_calendar_view: Callable[[str], bool],
) -> None:
    if (
        visual_state.calendar_visible
        or looks_like_calendar_view(visual_state.primary_view)
        or normalize_text(visual_state.selected_sidebar_item).lower() == "calendar"
    ):
        run_state.calendar_visible_verified = True
        append_evidence(run_state, "The Calendar module is visibly open in the current screenshot.")

    if visual_state.calendar_today_highlighted:
        run_state.calendar_today_highlighted_verified = True
        if visual_state.calendar_today_label:
            run_state.calendar_today_label = visual_state.calendar_today_label
        append_evidence(
            run_state,
            f"Today's blue-highlighted calendar date is visible{f': {run_state.calendar_today_label}' if run_state.calendar_today_label else ''}.",
        )

    if visual_state.calendar_event_editor_visible:
        run_state.calendar_event_editor_verified = True
        run_state.current_stage = "verify"
        run_state.calendar_event_title_current = visual_state.calendar_event_editor_title_text
        if (
            run_state.calendar_event_title_target
            and visual_state.calendar_event_editor_title_text
            and normalize_text(visual_state.calendar_event_editor_title_text) == normalize_text(run_state.calendar_event_title_target)
        ):
            run_state.calendar_event_title_typed_verified = True
            append_evidence(
                run_state,
                f"The calendar event editor visibly contains the requested title {run_state.calendar_event_title_target!r}.",
            )
        if (
            run_state.calendar_target_time_hint
            and visual_state.calendar_event_time_range
            and calendar_time_range_matches_hint(
                visual_state.calendar_event_time_range,
                run_state.calendar_target_time_hint,
                normalize_text=normalize_text,
            )
        ):
            run_state.calendar_time_range_verified = True
            append_evidence(
                run_state,
                f"The calendar event editor time range {visual_state.calendar_event_time_range!r} matches the requested time hint {run_state.calendar_target_time_hint!r}.",
            )
        if visual_state.calendar_event_time_range:
            append_evidence(
                run_state,
                f"A new calendar event editor is open with visible time range {visual_state.calendar_event_time_range!r}.",
            )
        else:
            append_evidence(run_state, "A new calendar event editor is visibly open.")

    if (
        run_state.calendar_slot_action_count <= 0
        and run_state.calendar_save_actions <= 0
        and visual_state.calendar_saved_event_visible
        and (
            not run_state.calendar_event_title_target
            or normalize_text(visual_state.calendar_saved_event_title) == normalize_text(run_state.calendar_event_title_target)
        )
    ):
        run_state.calendar_preexisting_matching_event_visible = True
        append_evidence(
            run_state,
            "A matching calendar event tile is already visible before this run performs any slot-click or Save action. Treating it as baseline only.",
        )

    if (
        run_state.calendar_save_actions > 0
        and visual_state.calendar_saved_event_visible
        and (
            not run_state.calendar_event_title_target
            or normalize_text(visual_state.calendar_saved_event_title) == normalize_text(run_state.calendar_event_title_target)
        )
    ):
        run_state.calendar_event_saved_verified = True
        run_state.current_stage = "verify"
        if visual_state.calendar_saved_event_title:
            append_evidence(
                run_state,
                f"The saved calendar event {visual_state.calendar_saved_event_title!r} is visibly present in the calendar grid.",
            )
        else:
            append_evidence(run_state, "A saved calendar event is visibly present in the calendar grid.")


def refresh_calendar_done_gate(run_state: Any) -> bool:
    if run_state.goal_kind == "open_calendar":
        if not run_state.calendar_visible_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The Calendar module is not visibly open yet."
            return True
        if not run_state.perception_stable:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The visual completion signal is not stable across observations yet."
            return True
        run_state.done_gate_ready = True
        run_state.done_gate_reason = "The Calendar module is visibly open and stable."
        return True

    if run_state.goal_kind == "create_calendar_event":
        if not run_state.calendar_visible_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The Calendar module is not visibly open yet."
            return True
        if not run_state.calendar_today_highlighted_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "Today's blue-highlighted calendar date has not been visually identified yet."
            return True
        if run_state.calendar_slot_action_count <= 0:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run has not clicked a calendar time slot yet."
            return True
        if run_state.calendar_target_time_hint and not run_state.calendar_time_range_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = f"The selected calendar time range does not yet visibly match the requested hint {run_state.calendar_target_time_hint!r}."
            return True
        if not run_state.calendar_event_editor_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The new calendar event editor is not visibly open yet."
            return True
        if run_state.calendar_event_title_target and not run_state.calendar_event_title_typed_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = f"The calendar event title {run_state.calendar_event_title_target!r} is not visibly typed in the editor yet."
            return True
        if run_state.calendar_save_actions <= 0:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "This run has not clicked Save in the calendar event editor yet."
            return True
        if not run_state.calendar_event_saved_verified:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The saved calendar event is not visibly present in the calendar grid yet."
            return True
        if not run_state.perception_stable:
            run_state.done_gate_ready = False
            run_state.done_gate_reason = "The visual completion signal is not stable across observations yet."
            return True
        run_state.done_gate_ready = True
        run_state.done_gate_reason = "Calendar event creation was completed, saved, and the new event is visibly present in the calendar grid."
        return True

    return False


def describe_calendar_visual_state(run_state: Any) -> str | None:
    visual_state = run_state.last_visual_state or {}
    if not visual_state:
        return None
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
    if bool(visual_state.get("calendar_visible", False)):
        if bool(visual_state.get("calendar_today_highlighted", False)):
            label = str(visual_state.get("calendar_today_label", "")).strip()
            return f"calendar visible with today highlighted{f' ({label})' if label else ''}"
        return "calendar visible"
    return None


def is_calendar_slot_action(action: Any, *, normalize_text: Callable[[str], str]) -> bool:
    if getattr(action, "type", "") != "click":
        return False
    target = normalize_text(str(getattr(action, "target", ""))).lower()
    keywords = (
        "time slot",
        "timeslot",
        "slot",
        "today column",
        "week grid",
        "calendar grid",
        "empty time",
        "鏃堕棿鑺傜偣",
        "鏃堕棿妲?",
        "鏃ュ巻缃戞牸",
        "鏃ユ湡鍒?",
    )
    return any(keyword in target for keyword in keywords)


def is_calendar_save_action(action: Any, *, normalize_text: Callable[[str], str]) -> bool:
    action_type = getattr(action, "type", "")
    target = normalize_text(str(getattr(action, "target", ""))).lower()
    if action_type == "click" and "save" in target:
        return True
    if action_type == "hotkey":
        keys = [str(key).lower() for key in (getattr(action, "keys", None) or [])]
        return keys in (["command", "s"], ["ctrl", "s"])
    return False


def calendar_time_range_matches_hint(
    visible_range: str,
    hint: str,
    *,
    normalize_text: Callable[[str], str],
) -> bool:
    if not visible_range or not hint:
        return False
    normalized_range = normalize_text(visible_range).lower()
    normalized_hint = normalize_text(hint).lower()
    if normalized_hint in normalized_range:
        return True

    hint_minutes = extract_time_candidates_in_minutes(hint)
    range_minutes = extract_time_candidates_in_minutes(visible_range)
    if not hint_minutes or not range_minutes:
        return False

    first_hint = hint_minutes[0]
    return any(abs(candidate - first_hint) <= 5 for candidate in range_minutes)


def extract_time_candidates_in_minutes(text: str) -> list[int]:
    candidates: list[int] = []
    lower = text.lower()

    for match in re.finditer(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", lower):
        hour = int(match.group(1))
        minute = int(match.group(2))
        meridiem = match.group(3)
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        candidates.append(hour * 60 + minute)

    for match in re.finditer(r"(\d{1,2})鐐??:(\d{1,2})鍒?)?", text):
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        candidates.append(hour * 60 + minute)

    unique: list[int] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique
