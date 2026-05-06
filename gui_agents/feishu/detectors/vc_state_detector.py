"""Metadata-first state detector for Feishu Video Conference."""

from __future__ import annotations

from typing import Any

from gui_agents.feishu.contracts import FeishuState
from gui_agents.feishu.detectors.anomaly import merge_anomaly_product_state
from gui_agents.feishu.observation import normalize_observation
from gui_agents.feishu.pages.registry import get_page_descriptor


VC_HOME_KEYWORDS = ("视频会议", "发起会议", "加入会议", "历史记录")
VC_START_PREVIEW_KEYWORDS = ("开始会议", "麦克风", "摄像头")
VC_ACTIVE_KEYWORDS = ("会议信息", "布局", "AI 总结")
VC_INVITE_POPOVER_KEYWORDS = ("复制邀请链接",)
VC_INVITE_DIALOG_KEYWORDS = ("分享邀请", "电话邀请", "复制入会信息")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _state_from_metadata(metadata: dict[str, Any]) -> FeishuState:
    expected = metadata.get("expected_state", {})
    product_state = dict(metadata.get("product_state", {}))
    return FeishuState(
        page_type=expected.get("page_type") or metadata.get("page_type", "unknown"),
        product=expected.get("product") or metadata.get("product", "vc"),
        chat_name=None,
        message_input_visible=bool(expected.get("message_input_visible", False)),
        send_button_visible=bool(expected.get("send_button_visible", False)),
        search_box_visible=bool(expected.get("search_box_visible", False)),
        modal_type=expected.get("modal_type"),
        last_error_banner=expected.get("last_error_banner"),
        product_state=product_state,
    )


def _fallback_state(observation: dict[str, Any]) -> FeishuState:
    ocr_text = observation.get("ocr_text", "")
    page_id = None
    product_state: dict[str, Any] = {}
    modal_type = None

    if _contains_any(ocr_text, VC_INVITE_DIALOG_KEYWORDS):
        page_id = "vc_invite_dialog"
        modal_type = "vc_invite_dialog"
        product_state = {
            "invite_dialog_visible": True,
            "invite_search_visible": "搜索" in ocr_text,
            "share_button_visible": "分享" in ocr_text,
        }
    elif _contains_any(ocr_text, VC_INVITE_POPOVER_KEYWORDS) and "邀请" in ocr_text:
        page_id = "vc_meeting_active"
        modal_type = "vc_invite_popover"
        product_state = {
            "meeting_active": True,
            "invite_popover_visible": True,
            "invite_entry_visible": "邀请" in ocr_text,
            "copy_invite_link_visible": "复制邀请链接" in ocr_text,
        }
    elif "会议 ID" in ocr_text or "会议ID" in ocr_text:
        page_id = "vc_join_preview"
        product_state = {
            "join_preview_visible": True,
            "meeting_id_input_visible": True,
            "join_button_visible": "加入会议" in ocr_text,
        }
    elif _contains_any(ocr_text, VC_ACTIVE_KEYWORDS):
        page_id = "vc_meeting_active"
        product_state = {
            "meeting_active": True,
            "invite_button_visible": "邀请" in ocr_text,
        }
    elif "开始会议" in ocr_text and _contains_any(ocr_text, VC_START_PREVIEW_KEYWORDS):
        page_id = "vc_start_preview"
        product_state = {
            "start_preview_visible": True,
            "start_button_visible": True,
            "microphone_toggle_visible": "麦克风" in ocr_text,
            "camera_toggle_visible": "摄像头" in ocr_text,
        }
    elif _contains_any(ocr_text, VC_HOME_KEYWORDS):
        page_id = "vc_home"
        product_state = {
            "vc_home_visible": True,
            "start_card_visible": "发起会议" in ocr_text,
            "join_card_visible": "加入会议" in ocr_text,
            "history_visible": "历史记录" in ocr_text,
        }
    product_state = merge_anomaly_product_state(product_state, ocr_text)

    descriptor = get_page_descriptor(page_id) if page_id else None
    return FeishuState(
        page_type=descriptor["page_type"] if descriptor else "unknown",
        product="vc" if descriptor else "unknown",
        chat_name=None,
        message_input_visible=False,
        send_button_visible=False,
        search_box_visible=page_id in {"vc_home", "vc_invite_dialog"},
        modal_type=modal_type,
        last_error_banner=None,
        product_state=product_state,
    )


def detect_vc_state(observation: dict[str, Any]) -> FeishuState:
    metadata = normalize_observation(observation)
    if metadata:
        return _state_from_metadata(metadata)
    return _fallback_state(observation)
