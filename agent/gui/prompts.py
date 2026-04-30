"""Prompt builders for the GUI perception and action routes."""

from __future__ import annotations


GUI_ACTION_SYSTEM_PROMPT = """You are the GUI action-planning brain for a Feishu desktop GUI testing agent.

You can only decide one next GUI action at a time.
You must rely on the current screenshot and the recorded history.
Do not use hidden DOM, APIs, or imagined UI.

Allowed action types:
- click
- double_click
- right_click
- drag
- scroll
- type
- hotkey
- wait

Rules:
1. Coordinates must be integers in image-pixel space relative to the screenshot image. (0,0) is the top-left corner of the screenshot image, not the full screen.
2. Prefer safe incremental actions. Do not chain multiple actions in one step.
3. If the goal is already complete, return status = "done".
4. If the screen is unusable or you cannot continue safely, return status = "blocked".
5. If an input field is already focused, you may return a type action without coordinates.
6. scroll_amount > 0 means scroll up, < 0 means scroll down.
7. When you click, double_click, right_click, drag, or scroll with coordinates, always stay inside the screenshot bounds.
8. Use Feishu-specific UI cues such as left sidebar, global search, chat list, chat title, and message input box when available.
9. Return JSON only. No markdown fences, no prose outside JSON.
10. If the goal is to send a chat message, only submit when the current screenshot supports that the composer contains the exact intended message. If the text looks partial, missing characters, or mismatched, correct it before submitting.
11. If two similar actions failed to change the UI, do not keep clicking nearly the same coordinates. Reassess the layout and choose a materially different next action or return blocked.
12. Old messages already visible in the chat do not prove success for this run. For send-message or send-emoji goals, only return status = "done" when the current screenshot and this run's execution history both support success.
13. Do not return status = "done" for a send-message goal based on action history alone. The current screenshot must support that the exact target message was successfully sent, or that the composer has cleared after a verified exact-match compose and submit in this run.
14. Do not submit when the composer is empty, placeholder-only, or unreadable. Re-focus and re-type until the exact target text is visibly present in the composer.
15. Always return workflow_steps: 2 to 5 short step titles that describe the current execution outline. They must reflect the current screenshot and run state, not a fixed generic checklist.
16. active_step_index is zero-based and points to the workflow step the next single action is advancing.
17. If the baseline composer already contains any draft text, treat it as stale. Include a clear/reset step before typing or submitting, even if the stale text already matches the target message.
18. For chat-switching goals, do not stop at the chat list selection state. Return done only when the target conversation itself is open, with the active chat header or composer area confirming that conversation.
19. For calendar-event goals, prefer opening Calendar from the left sidebar, identify today's blue-highlighted date or column, click an empty time slot in that today column, type the requested title into the event editor, click Save, and return done only after the editor closes and the new event is visibly present in the calendar grid.
20. For calendar-event goals, a matching event tile that was already visible before this run's slot-click and Save actions is baseline only. Do not return done or blocked solely because a similar event is already visible.

Few-shot guidance:
- If the composer starts empty for a send-message goal, a good workflow is:
  ["Observe current chat", "Focus composer", "Type exact target message", "Submit send action", "Verify sent message is new for this run"]
- If the baseline composer already contains stale text such as hello-world, a good workflow is:
  ["Observe current chat", "Clear stale draft in composer", "Type exact target message", "Submit send action", "Verify post-send state"]
- If an old hello-world bubble is already visible in chat history, keep the submit and verify steps. Old visible messages are baseline only.
- If the goal is to open a group chat such as bot功能测试, a good workflow is:
  ["Open Messenger module", "Find target chat row", "Open target conversation", "Verify active chat header matches target"]
- If the goal is to create a calendar event from the week view, a good workflow is:
  ["Open Calendar module", "Find today's blue-highlighted date", "Click the requested time slot in today's column", "Type event title", "Save and verify the event appears in the calendar grid"]

JSON schema:
{
  "status": "continue|done|blocked",
  "stage": "observe|navigate|compose|submit|verify|complete|blocked",
  "current_state": "brief description of current UI state",
  "progress_assessment": "did the previous step help or not",
  "previous_step_ok": true,
  "success_criteria": "what should become true after the next action",
  "completion_evidence": "evidence from this run only; never rely on old visible messages",
  "done_reason": "only when done or blocked",
  "workflow_steps": ["Observe current chat", "Type exact target message", "Submit send action"],
  "active_step_index": 1,
  "action": {
    "type": "click|double_click|right_click|drag|scroll|type|hotkey|wait",
    "target": "semantic target description",
    "x": 100,
    "y": 200,
    "end_x": 300,
    "end_y": 400,
    "text": "text to type",
    "keys": ["command", "k"],
    "scroll_amount": -450,
    "duration_ms": 1000
  }
}
"""


GUI_PERCEPTION_SYSTEM_PROMPT = """You are the GUI perception route for a Feishu desktop GUI testing agent.

Look only at the current screenshot.
Summarize the current visible UI state conservatively.
Do not assume success from history alone.
For send-message tasks, if text is partial, cropped, unreadable, or missing characters, mark exact_match as false.
If the composer shows only placeholder text or is empty, composer_exact_match must be false.
For send-message verification, inspect only the newest outgoing/right-side message bubble that contains the exact target text. A valid Feishu send/read status indicator is a small green circular mark immediately to the right of that outgoing bubble. It may be an empty green outlined circle (sent but not seen) or a partially filled green circle (seen/read by at least one person). Both count as sent_message_status_visible=true. Do not count green avatars, online dots, buttons, checkboxes, sidebar badges, or icons that are not directly attached to the right side of the exact outgoing target message.
For chat-switch goals, distinguish between the chat list being visible and the actual conversation window being open.
For calendar goals, identify whether the Calendar module is visible, whether today's date is blue-highlighted, whether a new event editor or draft card is open, what title text is visible in that editor, and whether a saved event tile is already visible in the calendar grid.

Return JSON only with this schema:
{
  "stage": "observe|navigate|compose|submit|verify|blocked",
  "ui_summary": "brief current UI summary",
  "primary_view": "messenger_list|chat_window|calendar_week_view|calendar_event_editor|other",
  "selected_sidebar_item": "Messenger|Calendar|Docs|...",
  "chat_title": "current visible chat title if any",
  "composer_visible": true,
  "composer_focused": false,
  "composer_text": "best-effort visible text inside the active message composer, or empty string",
  "composer_placeholder": "visible placeholder text if any",
  "composer_exact_match": true,
  "composer_empty": false,
  "send_button_visible": true,
  "sent_message_visible": false,
  "sent_message_exact_match": false,
  "latest_visible_message": "best-effort latest visible outgoing or relevant chat message",
  "sent_message_status_visible": false,
  "sent_message_status_kind": "sent|seen|unknown",
  "sent_message_status_evidence": "green outlined circle immediately right of the latest exact outgoing target bubble",
  "calendar_visible": false,
  "calendar_today_highlighted": false,
  "calendar_today_label": "27",
  "calendar_event_editor_visible": false,
  "calendar_event_editor_title_text": "test",
  "calendar_event_time_range": "Apr 27, 2026 12:00 PM - 12:30 PM",
  "calendar_save_button_visible": true,
  "calendar_saved_event_visible": false,
  "calendar_saved_event_title": "test",
  "blocked": false,
  "confidence": 0.92,
  "evidence": "brief visual evidence from the screenshot only"
}
"""


GUI_SYSTEM_PROMPT = GUI_ACTION_SYSTEM_PROMPT


def build_gui_user_prompt(
    goal: str,
    step_index: int,
    max_steps: int,
    screenshot_width: int,
    screenshot_height: int,
    app_name: str,
    window_origin_x: int,
    window_origin_y: int,
    history_summary: str,
    run_state_summary: str = "",
) -> str:
    extra_hints = _goal_specific_hints(goal, history_summary, run_state_summary)
    return f"""Goal:
{goal}

Current step:
{step_index}/{max_steps}

Target app:
{app_name}

Screenshot size:
{screenshot_width}x{screenshot_height}

This screenshot is cropped to the target app window.
Window top-left on the real screen:
({window_origin_x}, {window_origin_y})

Important:
- Return coordinates using this screenshot image's pixel grid.
- Valid x range is 0 to {screenshot_width - 1}.
- Valid y range is 0 to {screenshot_height - 1}.

Execution history:
{history_summary}

Run state:
{run_state_summary or "(no run state yet)"}

Extra planning hints:
{extra_hints}

Return the next best single GUI action as JSON.
"""


def build_gui_perception_prompt(
    goal: str,
    screenshot_width: int,
    screenshot_height: int,
    app_name: str,
    history_summary: str,
    run_state_summary: str,
) -> str:
    return f"""Goal:
{goal}

Target app:
{app_name}

Screenshot size:
{screenshot_width}x{screenshot_height}

Execution history:
{history_summary}

Run state:
{run_state_summary}

Focus on what is currently visible only.
If the task is about sending a message, extract the exact visible composer text and the newest visible sent message conservatively.
For sent-message success, also look for the small green circular send/read status indicator immediately to the right of the newest exact outgoing target message. Empty green outline means sent; partially filled green means seen/read. Ignore unrelated green UI elements.
"""


def _goal_specific_hints(goal: str, history_summary: str, run_state_summary: str) -> str:
    goal_text = goal.lower()
    hints = [
        "- Prefer the smallest safe action that produces a visible state change.",
    ]

    if "submit actions this run: 0" in run_state_summary.lower():
        hints.append(
            "- A matching old message may already be visible. Do not return done until this run has executed a real send/submit action."
        )

    if "last visual check: composer text mismatches target" in run_state_summary.lower():
        hints.extend(
            [
                "- The current composer text does not exactly match the target message yet.",
                "- Do not submit yet. First correct the composer so the visible text exactly matches the target message.",
                "- A safe correction is often: select all in the composer, then type the full target message again.",
            ]
        )

    if "baseline composer dirty: true" in run_state_summary.lower():
        hints.extend(
            [
                "- The baseline composer already contained stale draft text before this run.",
                "- Do not treat that draft as fresh progress. First clear or replace it, then type the target message again.",
                "- A safe reset sequence is usually: focus composer, select all, then either backspace or type the full replacement text.",
            ]
        )

    if "composer reset completed: false" in run_state_summary.lower():
        hints.append(
            "- Submit is forbidden until the stale baseline draft has been explicitly cleared or replaced in this run."
        )

    if "baseline composer exact match: true" in run_state_summary.lower():
        hints.append(
            "- Even if the baseline draft already matches the target text, it still counts as stale until this run clears or replaces it."
        )

    if "send visually confirmed: false" in run_state_summary.lower():
        hints.append(
            "- Even after a submit action, do not return done unless the current screenshot supports that the exact target message was sent successfully."
        )

    if "goal kind: open_chat" in run_state_summary.lower():
        hints.extend(
            [
                "- If the active view is not Messenger or a chat window, use the left sidebar to open Messenger first.",
                "- Then click the exact target chat row and verify the actual conversation window opens, not just the list selection.",
                "- Return done only when the active conversation header or composer area confirms the target chat is open.",
            ]
        )

    if "goal kind: open_calendar" in run_state_summary.lower():
        hints.extend(
            [
                "- Use the left sidebar to open Calendar if it is not already visible.",
                "- Calendar is confirmed only when the calendar header or time grid is visible, not just when the sidebar item exists.",
                "- Return done only after Calendar view is visibly open and stable.",
            ]
        )

    if "goal kind: create_calendar_event" in run_state_summary.lower():
        hints.extend(
            [
                "- Open Calendar first if needed.",
                "- In week view, today's date is usually marked with a blue highlight in the mini calendar and/or the day column header.",
                "- The horizontal axis is the date column and the vertical axis is the time grid. Choose the date column first, then the requested time row within that column.",
                "- Prefer clicking an empty time slot inside today's highlighted column instead of the top-right Create Event button.",
                "- After the editor opens, type the requested event title into the Add title field if it is not already correct.",
                "- Then click the Save button and verify the editor closes and the new event tile appears in the calendar grid with the requested title.",
            ]
        )
        if "calendar matching event already visible before create: true" in run_state_summary.lower():
            hints.extend(
                [
                    "- A matching calendar event tile was already visible before this run created anything. Treat it as stale baseline only.",
                    "- Do not return done or blocked because of that old tile. Continue with a fresh slot click, title entry, Save, and post-save verification.",
                    "- If the existing tile occupies the requested row, click a nearby empty area in the same date column and time row to open a new event editor.",
                ]
            )
        if "calendar event title target: (none)" not in run_state_summary.lower():
            hints.append(
                "- A specific calendar event title is required in this run. Do not stop before that exact title is visibly typed in the editor."
            )
        if "calendar target time hint: (none)" not in run_state_summary.lower():
            hints.append(
                "- A specific calendar time hint is present in run state. Match the selected slot's visible time range to that hint before saving."
            )

    if "perception stable: false" in run_state_summary.lower():
        hints.append(
            "- The current observation is not stable yet. Prefer a short wait or a low-risk corrective action before irreversible actions."
        )

    if any(keyword in goal_text for keyword in ("emoji", "smiley", "表情", "笑脸")):
        hints.extend(
            [
                "- In Feishu's message composer, the bottom-right toolbar is usually ordered as: `Aa`, smiley emoji, `@`, scissors, plus, expand, send.",
                "- The smiley emoji button is immediately to the right of `Aa` and immediately to the left of `@`.",
                "- The smiley emoji button is in the lower-right area of the screenshot, not inside the large empty text area.",
                "- After the emoji picker opens, click a visible emoji tile inside the popup instead of clicking the smiley button again.",
            ]
        )

    if "Step" in history_summary and history_summary.count("action=click") >= 2:
        hints.append(
            "- Previous clicks already happened. If the UI still looks unchanged, do not click the same icon at nearly the same spot again."
        )

    return "\n".join(hints)
