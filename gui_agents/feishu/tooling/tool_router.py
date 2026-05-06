"""State-aware Feishu tool routing for the S3 worker."""

from __future__ import annotations

import re
from typing import Iterable

from gui_agents.feishu.contracts import FeishuState
from gui_agents.feishu.detectors.calendar_state_detector import detect_calendar_state
from gui_agents.feishu.detectors.base_state_detector import detect_base_state
from gui_agents.feishu.detectors.docs_state_detector import detect_docs_state
from gui_agents.feishu.detectors.im_state_detector import detect_feishu_state
from gui_agents.feishu.detectors.vc_state_detector import detect_vc_state

from .tool_contracts import FeishuToolRecommendation
from .tool_registry import get_tool_specs


COMPOSE_MESSAGE_KEYWORDS = (
    "发送",
    "发消息",
    "回复",
    "消息",
    "输入",
)

SEND_MESSAGE_KEYWORDS = (
    "发送",
    "回复",
    "回车",
    "enter",
)

SEARCH_KEYWORDS = (
    "搜索",
    "查找",
    "检索",
    "定位",
)

EMOJI_KEYWORDS = (
    "表情",
    "emoji",
    "颜文字",
)

OPEN_CHAT_KEYWORDS = (
    "群",
    "群聊",
    "会话",
    "聊天",
    "消息中的",
)

BROWSER_SURFACE_KEYWORDS = (
    "多维表格",
    "Base",
    "base",
    "文档",
    "云文档",
    "分享",
    "浏览器",
)

DOCS_KEYWORDS = (
    "云文档",
    "飞书云文档",
    "新建文档",
    "空白文档",
    "文档页面",
    "文档中",
    "文档标题",
)

CALENDAR_KEYWORDS = (
    "日历",
    "日程",
    "会议室",
    "创建日程",
    "添加主题",
    "保存",
)

VC_KEYWORDS = (
    "视频会议",
    "发起会议",
    "发起视频会议",
    "开始会议",
    "开始视频会议",
    "加入会议",
    "加入视频会议",
    "会议 ID",
    "会议ID",
    "会议号",
    "邀请",
)


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _ordered_unique(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)


def _remove_tool(items: list[str], tool_name: str) -> None:
    while tool_name in items:
        items.remove(tool_name)


def _detect_intents(instruction: str) -> set[str]:
    intents: set[str] = set()
    if _contains_any(instruction, COMPOSE_MESSAGE_KEYWORDS):
        intents.add("compose_message")
    if _contains_any(instruction, SEND_MESSAGE_KEYWORDS):
        intents.add("send_message")
    if _contains_any(instruction, SEARCH_KEYWORDS):
        intents.add("search")
    if _contains_any(instruction, EMOJI_KEYWORDS):
        intents.add("emoji")
    if _contains_any(instruction, OPEN_CHAT_KEYWORDS):
        intents.add("open_chat")
    if _contains_any(instruction, BROWSER_SURFACE_KEYWORDS):
        intents.add("browser_surface")
    if _contains_any(instruction, DOCS_KEYWORDS):
        intents.add("docs")
    if _contains_any(instruction, ("创建", "新建")) and _contains_any(
        instruction, DOCS_KEYWORDS
    ):
        intents.add("create_doc")
    if _contains_any(instruction, CALENDAR_KEYWORDS):
        intents.add("calendar")
    if _contains_any(instruction, VC_KEYWORDS):
        intents.add("video_meeting")
    if _contains_any(
        instruction, ("发起会议", "发起视频会议", "开始会议", "开始视频会议")
    ):
        intents.add("start_video_meeting")
    if _contains_any(
        instruction, ("加入会议", "加入视频会议", "会议 ID", "会议ID", "会议号")
    ):
        intents.add("join_video_meeting")
    if _contains_any(instruction, ("邀请", "分享邀请", "复制邀请")):
        intents.add("invite_video_meeting")
    return intents


def _extract_target_chat_name(instruction: str) -> str | None:
    patterns = (
        r'(?:打开消息中的|打开|进入)\s*[""]([^""\n]+?)[""]?(?:群聊|群|会话|聊天)',
        r'(?:在|向|给)\s*[""]([^""\n]+)[""]\s*(?:群聊|群|会话|聊天)?(?:中)?(?:发送|发|回复)',
        r'(?:在|向|给)\s*[""]?([^""\n]+?)[""]?(?:群聊|群|会话|聊天)?(?:中)?(?:发送|发|回复)',
    )
    for pattern in patterns:
        match = re.search(pattern, instruction)
        if match:
            return match.group(1).strip()
    return None


def _build_state_summary(state: FeishuState) -> str:
    parts = [
        f"page_type={state.get('page_type', 'unknown')}",
        f"product={state.get('product', 'unknown')}",
    ]
    if state.get("modal_type"):
        parts.append(f"modal={state['modal_type']}")
    if state.get("chat_name"):
        parts.append(f"chat={state['chat_name']}")
    if state.get("message_input_visible"):
        parts.append("message_input=visible")
    if state.get("send_button_visible"):
        parts.append("send_button=visible")
    if state.get("search_box_visible"):
        parts.append("search_box=visible")

    product_state = state.get("product_state", {})
    if product_state.get("draft_present"):
        parts.append("draft=present")
    if product_state.get("send_button_enabled"):
        parts.append("send_button=enabled")
    if product_state.get("local_search_result_list_visible"):
        parts.append("conversation_search_results=visible")
    if product_state.get("search_result_list_visible"):
        parts.append("global_search_results=visible")
    if product_state.get("calendar_home_visible"):
        parts.append("calendar_home_visible")
    if product_state.get("event_modal_visible"):
        parts.append("calendar_event_modal_visible")
    if product_state.get("quick_add_visible"):
        parts.append("calendar_quick_add_visible")
    if product_state.get("date_picker_visible"):
        parts.append("calendar_date_picker_visible")
    if product_state.get("create_event_button_visible"):
        parts.append("create_event_button_visible")
    if product_state.get("title_input_visible"):
        parts.append("title_input_visible")
    if product_state.get("save_button_visible"):
        parts.append("save_button_visible")
    if product_state.get("meeting_active"):
        parts.append("meeting_active")
    if product_state.get("start_button_visible"):
        parts.append("start_button_visible")
    if product_state.get("join_button_visible"):
        parts.append("join_button_visible")
    if product_state.get("join_button_enabled"):
        parts.append("join_button_enabled")
    if product_state.get("invite_popover_visible"):
        parts.append("invite_popover_visible")
    if product_state.get("invite_dialog_visible"):
        parts.append("invite_dialog_visible")
    if product_state.get("blocking_modal_visible"):
        parts.append("blocking_modal_visible")
    if product_state.get("permission_denied_visible"):
        parts.append("permission_denied_visible")
    if product_state.get("loading_visible"):
        parts.append("loading_visible")
    if product_state.get("wrong_surface"):
        parts.append("wrong_surface")
    if product_state.get("recovery_hint"):
        parts.append(f"recovery_hint={product_state['recovery_hint']}")

    return ", ".join(parts)


def _apply_anomaly_guidance(
    product_state: dict,
    enabled_tools: list[str],
    preferred_tools: list[str],
    hints: list[str],
    rationale: list[str],
) -> str | None:
    recovery_hint = product_state.get("recovery_hint")
    if not recovery_hint:
        return None

    hints.append(
        f"Anomaly detected: recovery_hint={recovery_hint}. Treat this as semantic recovery guidance and re-check the screenshot before acting."
    )
    rationale.append(
        "The current surface exposes an abnormal or blocking state, so recovery guidance takes priority over normal page progression."
    )

    if product_state.get("permission_denied_visible"):
        enabled_tools.extend(["click", "wait"])
        preferred_tools.insert(1, "wait")
        hints.append(
            "A permission-denied surface is visible. Report the permission blocker or use a visible request-permission control if the screenshot clearly offers one."
        )
        return "request_permission_or_report_blocker"

    if product_state.get("wrong_surface"):
        enabled_tools.extend(["click", "hotkey", "wait"])
        preferred_tools.insert(1, "feishu_click")
        hints.append(
            "The current surface appears deleted, archived, or missing. Navigate back to the correct visible Feishu surface before continuing the task."
        )
        return "navigate_to_correct_surface"

    if product_state.get("loading_visible"):
        enabled_tools.append("wait")
        preferred_tools.insert(1, "wait")
        hints.append(
            "A loading state is visible. Prefer waiting briefly and observing again before choosing a product-specific action."
        )
        return "wait_for_loading_to_complete"

    if product_state.get("blocking_modal_visible"):
        enabled_tools.extend(["click", "wait"])
        preferred_tools.insert(1, "wait")
        preferred_tools.insert(2, "click")
        hints.append(
            "A blocking modal appears to be visible. Decide from the visible modal text whether to wait, dismiss, retry, or stop for user help."
        )
        return "dismiss_blocking_modal"

    return "current_recovery_surface"


def route_feishu_tools(
    instruction: str,
    observation: dict,
    state: FeishuState | None = None,
) -> FeishuToolRecommendation:
    if state is None:
        if _contains_any(instruction, VC_KEYWORDS):
            state = detect_vc_state(observation)
        elif _contains_any(instruction, DOCS_KEYWORDS):
            state = detect_docs_state(observation)
        elif _contains_any(instruction, CALENDAR_KEYWORDS):
            state = detect_calendar_state(observation)
        elif _contains_any(instruction, ("多维表格", "Base", "base")):
            state = detect_base_state(observation)
        else:
            state = detect_feishu_state(observation)
    page_type = state.get("page_type", "unknown")
    intents = _detect_intents(instruction)
    primary_intent = sorted(intents)[0] if intents else "general_feishu_task"
    target_chat_name = _extract_target_chat_name(instruction)
    detected_chat_name = state.get("chat_name")
    product_state = state.get("product_state", {})
    draft_present = bool(product_state.get("draft_present"))

    enabled_tools = ["feishu_focus", "feishu_click", "feishu_type", "hotkey", "wait"]
    preferred_tools = ["feishu_focus"]
    discouraged_tools: list[str] = []
    hints: list[str] = []
    rationale: list[str] = []
    next_step_focus = "current_feishu_surface"
    anomaly_next_step_focus = _apply_anomaly_guidance(
        product_state,
        enabled_tools,
        preferred_tools,
        hints,
        rationale,
    )

    if page_type == "shell_search":
        preferred_tools.extend(["feishu_type", "feishu_click", "hotkey"])
        discouraged_tools.extend(["click", "type"])
        next_step_focus = "global_search_entry"
        rationale.append(
            "Global Feishu search is visible, so text-driven UIA search is safer than generic visual clicks."
        )
        hints.append(
            'Use `agent.feishu_type(target, "搜索", overwrite=True, enter=True)` to refine or launch global search.'
        )
        hints.append(
            "After results appear, click the exact result text with `agent.feishu_click(...)` instead of a generic grounded click."
        )
        if target_chat_name:
            hints.append(f"Instruction target chat hint: {target_chat_name}.")

    elif state.get("product") == "docs":
        enabled_tools.extend(["click", "type", "feishu_doc_click", "feishu_doc_type"])
        preferred_tools.extend(["feishu_doc_click", "feishu_doc_type", "click", "type"])
        next_step_focus = "docs_visible_control"
        rationale.append(
            "Docs should be handled as agent-guided visible-state navigation, not a fixed create-document workflow."
        )
        hints.append(
            "Use Docs page-state cues from the current screenshot; do not assume the next step from a prebuilt ordered TestCase."
        )
        if page_type == "docs_home":
            next_step_focus = "docs_home_new_entry"
            hints.append(
                "On Docs home, use the visible New entry point or document list controls, then re-check the screenshot before choosing the document type."
            )
        elif page_type == "docs_new_dropdown":
            next_step_focus = "docs_new_document_option"
            hints.append(
                "The Docs new menu is visible. Choose the visible Document option if the task asks for a normal cloud document."
            )
        elif page_type == "docs_template_gallery":
            next_step_focus = "docs_blank_document_template"
            hints.append(
                "The template gallery is visible. Prefer the visible blank document template when the user asks to create a blank document."
            )
        elif page_type == "docs_browser_editor":
            next_step_focus = "docs_editor_title_or_body"
            hints.append(
                "The Docs editor is visible. Use the visible title/body fields; prefer `agent.feishu_doc_type(...)` for focused Docs text entry when appropriate."
            )
            if "create_doc" in intents:
                hints.append(
                    "If the editor is already open, skip earlier create-menu steps and continue with the title or body requested by the user."
                )
        else:
            hints.append(
                "First classify whether Docs home, new menu, template gallery, or editor is visible, then act only on current visible controls."
            )

    elif state.get("product") == "vc":
        enabled_tools.extend(
            [
                "click",
                "type",
                "feishu_vc_click_start_card",
                "feishu_vc_click_join_card",
                "feishu_vc_click_start_button",
                "feishu_vc_type_meeting_id",
                "feishu_vc_click_join_button",
                "feishu_vc_click_invite_button",
                "feishu_vc_click_invite_entry",
                "feishu_vc_click_share_button",
            ]
        )
        preferred_tools.extend(["feishu_click", "feishu_type", "click", "type"])
        next_step_focus = "video_meeting_visible_control"
        rationale.append(
            "Video meeting support is handled by feishu_agent tool guidance, not a fixed workflow stage machine."
        )
        if page_type == "vc_home":
            if "join_video_meeting" in intents:
                next_step_focus = "join_meeting_card"
                preferred_tools.insert(1, "feishu_vc_click_join_card")
                preferred_tools.insert(2, "feishu_vc_type_meeting_id")
                preferred_tools.insert(3, "feishu_vc_click_join_button")
                hints.append(
                    "On the VC home page, prefer `agent.feishu_vc_click_join_card()` for the entry card, then continue from the visible join preview."
                )
            elif "start_video_meeting" in intents:
                next_step_focus = "start_meeting_card"
                preferred_tools.insert(1, "feishu_vc_click_start_card")
                preferred_tools.insert(2, "feishu_vc_click_start_button")
                hints.append(
                    "On the VC home page, prefer `agent.feishu_vc_click_start_card()` for the entry card and re-check the preview window before starting the meeting."
                )
            else:
                preferred_tools.insert(1, "feishu_vc_click_start_card")
                preferred_tools.insert(2, "feishu_vc_click_join_card")
                hints.append(
                    "Use the visible VC entry card that matches the user's intent; do not assume a prebuilt step sequence."
                )
        elif page_type == "vc_start_preview":
            next_step_focus = "start_meeting_button"
            preferred_tools.insert(1, "feishu_vc_click_start_button")
            hints.append(
                "The start preview is visible. Prefer `agent.feishu_vc_click_start_button()` for the primary action after checking the current visible preview state."
            )
        elif page_type == "vc_join_preview":
            next_step_focus = "meeting_id_input_or_join_button"
            preferred_tools.insert(1, "feishu_vc_type_meeting_id")
            preferred_tools.insert(2, "feishu_vc_click_join_button")
            discouraged_tools.append("type")
            hints.append(
                "The join preview is visible. Prefer `agent.feishu_vc_type_meeting_id(...)` for the meeting-ID input and `agent.feishu_vc_click_join_button()` for the primary button."
            )
        elif page_type == "vc_meeting_active" and (
            state.get("modal_type") == "vc_invite_popover"
            or product_state.get("invite_popover_visible")
        ):
            next_step_focus = "invite_popover_entry"
            preferred_tools.insert(1, "feishu_vc_click_invite_entry")
            hints.append(
                "The invite popover is already open. Prefer `agent.feishu_vc_click_invite_entry()` to continue into the full invite dialog."
            )
        elif page_type == "vc_meeting_active":
            if "invite_video_meeting" in intents:
                next_step_focus = "meeting_invite_control"
                preferred_tools.insert(1, "feishu_vc_click_invite_button")
                hints.append(
                    "The meeting is active. Prefer `agent.feishu_vc_click_invite_button()` for the invite toolbar control, then re-check whether a popover or full dialog opened."
                )
            else:
                next_step_focus = "active_meeting_toolbar"
                preferred_tools.insert(1, "click")
                hints.append(
                    "The meeting is already active. Continue from visible toolbar controls instead of restarting the meeting."
                )
        elif page_type == "vc_invite_dialog":
            next_step_focus = "invite_dialog_search_or_share"
            preferred_tools.insert(1, "feishu_type")
            preferred_tools.insert(2, "feishu_vc_click_share_button")
            hints.append(
                "The invite dialog is open. Use the visible search field or result list first, and prefer `agent.feishu_vc_click_share_button()` only after the recipient is already selected."
            )
        else:
            preferred_tools.insert(1, "click")
            hints.append(
                "For VC tasks, first classify the visible screen, then act through visible controls with Feishu helpers or grounded clicks."
            )

    elif state.get("product") == "base":
        enabled_tools.extend(["click", "type"])
        preferred_tools.extend(["click", "type", "hotkey"])
        discouraged_tools.extend(["feishu_click", "feishu_type"])
        next_step_focus = "base_browser_or_desktop_surface"
        rationale.append(
            "Base commonly runs inside a browser-like surface, so visual grounding and keyboard input are safer than text-only Feishu UIA helpers."
        )
        hints.append(
            "Use the visible Base surface cues in the current screenshot, such as New entry points, template cards, table grid, or popup blockers."
        )
        hints.append(
            "If a Base AI or onboarding popup blocks the grid, dismiss it only after confirming the Base table editor is visible."
        )

    elif state.get("product") == "calendar":
        enabled_tools.extend(["click", "type"])
        preferred_tools.extend(["feishu_click", "feishu_type", "click"])
        next_step_focus = "calendar_visible_control"
        rationale.append(
            "Calendar should be handled as an agent-guided state surface, not a fixed workflow stage machine."
        )
        if page_type == "calendar_home":
            next_step_focus = "calendar_home_controls"
            hints.append(
                "On Calendar home, prefer the visible Create Schedule control or the text anchors in the screenshot, then re-check the screen before the next action."
            )
            hints.append(
                "If the user asked to create an event, choose either the visible Create Schedule entry or a specific time slot based on the instruction, then let the next screenshot determine whether the full create dialog or quick-add popup is open."
            )
        elif page_type == "calendar_event_modal":
            next_step_focus = "calendar_event_modal_controls"
            hints.append(
                "The full create-event modal is visible from the Create Schedule entry. Use the visible title field, attendee field, time controls, and Save button according to the current screenshot."
            )
            hints.append(
                "Do not rely on precomputed coordinates or a fixed step chain; re-check the modal state before typing or saving."
            )
        elif page_type in {"calendar_quick_add_modal", "calendar_quick_add_attendee"}:
            next_step_focus = "calendar_quick_add_controls"
            hints.append(
                "The time-slot quick-add popup is visible. Treat this as the grid-click creation path, not the full Create Schedule dialog."
            )
            hints.append(
                "Use the visible quick-add title/time controls first; only use attendee controls if they are visible in the current screenshot."
            )
        elif page_type == "calendar_date_picker":
            next_step_focus = "calendar_date_picker_controls"
            hints.append(
                "A date picker is open from the Calendar header. This is date navigation, not event creation; choose a visible date or close/re-check before creating an event."
            )
        else:
            hints.append(
                "First classify whether Calendar home, the full create-event modal, the time-slot quick-add popup, or a date picker is visible, then use only the visible controls from the current screenshot."
            )

    elif page_type == "chat_search_panel":
        preferred_tools.extend(["feishu_type", "feishu_click", "hotkey"])
        discouraged_tools.extend(["type"])
        if "emoji" in intents:
            enabled_tools.append("click")
        next_step_focus = "conversation_search_entry_or_result"
        rationale.append(
            "The in-chat search panel is already open; stay inside this branch until it is closed or the required result is selected."
        )
        hints.append(
            'Use `agent.feishu_type(query, "搜索会话内容", overwrite=True, enter=False)` for the panel input.'
        )
        hints.append(
            "Use `agent.feishu_click(...)` with exact result text for visible search results."
        )
        hints.append(
            "If the search panel is blocking composer actions, close it before trying to type into the message box."
        )

    elif page_type == "chat_main":
        enabled_tools.extend(
            [
                "click",
                "feishu_click_message_input",
                "feishu_type_message",
                "feishu_click_send_button",
            ]
        )
        next_step_focus = "chat_main_primary_action"
        rationale.append(
            "The main IM chat surface is visible, so prefer Feishu desktop helpers before generic grounded actions."
        )

        if "search" in intents:
            preferred_tools.extend(["hotkey", "feishu_click", "feishu_type"])
            next_step_focus = "open_or_use_conversation_search"
            hints.append(
                "If you need in-chat search, prefer `agent.hotkey(['ctrl', 'f'])` or click the visible search control first."
            )

        if "open_chat" in intents:
            preferred_tools.extend(["feishu_click", "feishu_type"])
            hints.append(
                "When switching chats, click the exact conversation title in the left sidebar first; use search only if the target is not visible."
            )
            if target_chat_name:
                hints.append(f"Instruction target chat hint: {target_chat_name}.")

        if "compose_message" in intents or state.get("message_input_visible"):
            preferred_tools.insert(1, "feishu_type_message")
            preferred_tools.insert(2, "feishu_click_message_input")
            preferred_tools.append("hotkey")
            next_step_focus = "message_composer"
            hints.append(
                "For normal IM typing, prefer `agent.feishu_type_message(...)` instead of describing the input box in natural language."
            )

        if (
            "send_message" in intents
            and state.get("send_button_visible")
            and draft_present
        ):
            preferred_tools.append("feishu_click_send_button")
            hints.append(
                "If a draft is already present, prefer `agent.hotkey(['enter'])`; if Enter is unsuitable, use `agent.feishu_click_send_button()`."
            )

        if "emoji" in intents and draft_present:
            _remove_tool(preferred_tools, "feishu_click")
            preferred_tools.insert(1, "click")
            discouraged_tools.extend(["feishu_click", "type"])
            next_step_focus = "emoji_icon_or_picker"
            hints.append(
                "For icon-only composer controls such as emoji, prefer a grounded `agent.click(...)` because `feishu_click(...)` is text-based and may miss icon-only buttons."
            )
        elif "emoji" in intents:
            hints.append(
                "Do not go to emoji first. Finish the message draft in the composer before opening the emoji picker."
            )

    else:
        enabled_tools.extend(
            [
                "click",
                "type",
                "feishu_click_message_input",
                "feishu_type_message",
            ]
        )
        preferred_tools.extend(["feishu_click", "feishu_type"])
        rationale.append(
            "The page is not confidently classified, so start from screenshot reasoning and then prefer dedicated Feishu helpers for known IM surfaces."
        )
        hints.append(
            "Re-check whether the IM composer is already visible before re-clicking chat titles or search entry points."
        )
        if ("compose_message" in intents and not draft_present) or state.get(
            "message_input_visible"
        ):
            preferred_tools.insert(1, "feishu_type_message")
            preferred_tools.insert(2, "feishu_click_message_input")
            next_step_focus = "message_composer"
            hints.append(
                "If the chat composer is visible, prefer `agent.feishu_type_message(...)` or `agent.feishu_click_message_input()` before using later-step tools."
            )
        if "emoji" in intents and draft_present:
            _remove_tool(preferred_tools, "feishu_click")
            preferred_tools.insert(1, "click")
            discouraged_tools.append("feishu_click")
            next_step_focus = "emoji_icon_or_picker"
            hints.append(
                "For emoji or other icon-only controls, do not assume `feishu_click(...)` can find them by text; prefer a grounded `agent.click(...)`."
            )
        elif "compose_message" in intents and not draft_present:
            hints.append(
                "If the active chat is already open, go directly to the composer instead of re-clicking the chat title."
            )
        if target_chat_name:
            hints.append(f"Instruction target chat hint: {target_chat_name}.")

    if anomaly_next_step_focus:
        next_step_focus = anomaly_next_step_focus

    preferred = _ordered_unique(preferred_tools)
    enabled = _ordered_unique(list(preferred) + enabled_tools)
    discouraged = _ordered_unique(discouraged_tools)

    return FeishuToolRecommendation(
        page_type=page_type,
        product=state.get("product", "unknown"),
        intent=primary_intent,
        params={"instruction": instruction},
        state_summary=_build_state_summary(state),
        next_step_focus=next_step_focus,
        enabled_tools=enabled,
        preferred_tools=preferred,
        discouraged_tools=discouraged,
        hints=tuple(hints),
        rationale=tuple(rationale),
        target_chat_name=target_chat_name,
        detected_chat_name=detected_chat_name,
    )


def build_feishu_tool_guidance(
    instruction: str,
    observation: dict,
    state: FeishuState | None = None,
) -> str:
    recommendation = route_feishu_tools(instruction, observation, state=state)
    lines = [
        "Use this only as recovery guidance after the previous action did not reach the expected state.",
        "Re-check the current screenshot before choosing the next tool.",
        "Prefer the listed tools when they match what you see, but do not override the screenshot.",
        f"Detected state: {recommendation.state_summary}",
        f"Intent: {recommendation.intent}",
        f"Next-step focus: {recommendation.next_step_focus}",
        "Preferred tools: " + ", ".join(recommendation.preferred_tools),
        "Allowed tools: " + ", ".join(recommendation.enabled_tools),
    ]
    if recommendation.discouraged_tools:
        lines.append(
            "Discouraged tools: " + ", ".join(recommendation.discouraged_tools)
        )
    if recommendation.detected_chat_name:
        lines.append(f"Detected active chat: {recommendation.detected_chat_name}")
    if recommendation.target_chat_name:
        lines.append(f"Instruction target chat: {recommendation.target_chat_name}")
    for rationale in recommendation.rationale:
        lines.append(f"Rationale: {rationale}")
    for hint in recommendation.hints:
        lines.append(f"Hint: {hint}")

    for spec in get_tool_specs(recommendation.preferred_tools[:3]):
        if spec.examples:
            lines.append(f"Example {spec.tool_name}: {spec.examples[0]}")

    return "\n".join(lines)
