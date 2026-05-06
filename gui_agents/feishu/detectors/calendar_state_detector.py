"""Metadata-first state detector for Feishu Calendar."""

from __future__ import annotations

from typing import Any

from gui_agents.feishu.contracts import FeishuState
from gui_agents.feishu.detectors.anomaly import merge_anomaly_product_state
from gui_agents.feishu.observation import normalize_observation
from gui_agents.feishu.pages.registry import get_page_descriptor


CALENDAR_HOME_KEYWORDS = ("日历", "会议室", "预约活动", "创建日程", "今天")
CALENDAR_EVENT_MODAL_KEYWORDS = ("创建日程", "添加主题", "保存", "取消")
CALENDAR_DATE_PICKER_KEYWORDS = ("2026 年", "5月", "今天")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _contains_all(text: str, keywords: tuple[str, ...]) -> bool:
    return all(keyword and keyword in text for keyword in keywords)


def _state_from_metadata(metadata: dict[str, Any]) -> FeishuState:
    expected = metadata.get("expected_state", {})
    return FeishuState(
        page_type=expected.get("page_type") or metadata.get("page_type", "unknown"),
        product=expected.get("product") or metadata.get("product", "calendar"),
        chat_name=None,
        message_input_visible=bool(expected.get("message_input_visible", False)),
        send_button_visible=bool(expected.get("send_button_visible", False)),
        search_box_visible=bool(expected.get("search_box_visible", False)),
        modal_type=expected.get("modal_type"),
        last_error_banner=expected.get("last_error_banner"),
        product_state=dict(metadata.get("product_state", {})),
    )


def _fallback_state(observation: dict[str, Any]) -> FeishuState:
    ocr_text = observation.get("ocr_text", "")
    page_id = None
    product_state: dict[str, Any] = {}

    if _contains_all(ocr_text, ("添加主题", "保存")) and (
        "添加日程" in ocr_text or "创建日程" not in ocr_text
    ):
        page_id = "calendar_quick_add_modal"
        product_state = {
            "quick_add_visible": True,
            "title_input_visible": "添加主题" in ocr_text,
            "attendee_input_visible": "添加联系人" in ocr_text,
            "time_controls_visible": True,
            "save_button_visible": "保存" in ocr_text,
        }
    elif _contains_any(ocr_text, CALENDAR_EVENT_MODAL_KEYWORDS):
        page_id = "calendar_event_modal"
        product_state = {
            "event_modal_visible": True,
            "title_input_visible": "添加主题" in ocr_text,
            "attendee_input_visible": "添加联系人" in ocr_text,
            "time_controls_visible": True,
            "save_button_visible": "保存" in ocr_text,
        }
    elif "今天" in ocr_text and _contains_any(ocr_text, CALENDAR_DATE_PICKER_KEYWORDS):
        page_id = "calendar_date_picker"
        product_state = {
            "calendar_home_visible": True,
            "date_picker_visible": True,
            "month_picker_visible": True,
            "today_shortcut_visible": True,
        }
    elif _contains_any(ocr_text, CALENDAR_HOME_KEYWORDS):
        page_id = "calendar_home"
        product_state = {
            "calendar_home_visible": True,
            "create_event_button_visible": "创建日程" in ocr_text,
        }
    product_state = merge_anomaly_product_state(product_state, ocr_text)

    descriptor = get_page_descriptor(page_id) if page_id else None
    return FeishuState(
        page_type=descriptor["page_type"] if descriptor else "unknown",
        product="calendar" if descriptor else "unknown",
        chat_name=None,
        message_input_visible=False,
        send_button_visible=False,
        search_box_visible=False,
        modal_type=(
            "create_event"
            if page_id == "calendar_event_modal"
            else (
                "quick_add_event"
                if page_id == "calendar_quick_add_modal"
                else "date_picker" if page_id == "calendar_date_picker" else None
            )
        ),
        last_error_banner=None,
        product_state=product_state,
    )


def detect_calendar_state(observation: dict[str, Any]) -> FeishuState:
    metadata = normalize_observation(observation)
    if metadata and metadata.get("product") == "calendar":
        return _state_from_metadata(metadata)
    return _fallback_state(observation)
