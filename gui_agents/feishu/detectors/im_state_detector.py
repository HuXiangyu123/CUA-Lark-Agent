"""Minimal Feishu state detector for Track B MVP."""

from __future__ import annotations

import re
from typing import Any

from gui_agents.feishu.contracts import FeishuState, PageDescriptor
from gui_agents.feishu.detectors.anomaly import merge_anomaly_product_state
from gui_agents.feishu.observation import normalize_observation
from gui_agents.feishu.pages.registry import get_page_descriptor


CHAT_PLACEHOLDER_KEYWORDS = ("发送给",)
MESSAGE_TAB_KEYWORDS = ("消息",)
SEND_BUTTON_KEYWORDS = ("发送",)
SHELL_SEARCH_KEYWORDS = (
    "问你想问的问题",
    "搜索关键词",
)
CHAT_SEARCH_PANEL_KEYWORDS = ("搜索会话内容",)
CHAT_SEARCH_FILTER_KEYWORDS = (
    "来自用户",
    "时间",
    "高级搜索",
)
CHAT_SEARCH_EMPTY_HINT_KEYWORDS = ("输入关键词或使用过滤器查找消息记录",)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _extract_chat_name(text: str) -> str | None:
    match = re.search(
        r"发送给\s*([^\n\r]+)",
        text,
    )
    if match:
        return match.group(1).strip()
    return None


def _state_from_metadata(metadata: dict[str, Any]) -> FeishuState:
    expected = metadata.get("expected_state", {})
    product_state = dict(metadata.get("product_state", {}))
    chat_name = expected.get("chat_name") or metadata.get("chat_name")
    if not chat_name:
        chat_name = _extract_chat_name(metadata.get("text_anchors_text", ""))

    return FeishuState(
        page_type=expected.get("page_type") or metadata.get("page_type", "unknown"),
        product=expected.get("product") or metadata.get("product", "im"),
        chat_name=chat_name,
        message_input_visible=bool(expected.get("message_input_visible", False)),
        send_button_visible=bool(expected.get("send_button_visible", False)),
        search_box_visible=bool(expected.get("search_box_visible", False)),
        modal_type=expected.get("modal_type"),
        last_error_banner=expected.get("last_error_banner"),
        product_state=product_state,
    )


def _shell_search_state(ocr_text: str) -> FeishuState:
    page_descriptor = get_page_descriptor("feishu_shell_search")
    product_state = merge_anomaly_product_state(
        {
            "search_result_list_visible": "常用" in ocr_text,
        },
        ocr_text,
    )
    return FeishuState(
        page_type=page_descriptor["page_type"] if page_descriptor else "unknown",
        product="feishu",
        chat_name=None,
        message_input_visible=False,
        send_button_visible=False,
        search_box_visible=True,
        modal_type=None,
        last_error_banner=None,
        product_state=product_state,
    )


def _im_chat_search_panel_state(ocr_text: str) -> FeishuState:
    page_descriptor = get_page_descriptor("im_chat_search_panel")
    product_state = merge_anomaly_product_state(
        {
            "local_search_panel_visible": True,
            "local_search_filters_visible": _contains_any(
                ocr_text, CHAT_SEARCH_FILTER_KEYWORDS
            ),
            "local_search_empty_hint_visible": _contains_any(
                ocr_text, CHAT_SEARCH_EMPTY_HINT_KEYWORDS
            ),
            "local_search_result_list_visible": False,
            "visible_conversation_search_results": [],
        },
        ocr_text,
    )
    return FeishuState(
        page_type=page_descriptor["page_type"] if page_descriptor else "unknown",
        product="im",
        chat_name=None,
        message_input_visible=False,
        send_button_visible=False,
        search_box_visible=True,
        modal_type=None,
        last_error_banner=None,
        product_state=product_state,
    )


def _im_chat_state(
    ocr_text: str, page_descriptor: PageDescriptor | None
) -> FeishuState:
    return FeishuState(
        page_type=page_descriptor["page_type"] if page_descriptor else "unknown",
        product="im",
        chat_name=_extract_chat_name(ocr_text),
        message_input_visible=_contains_any(ocr_text, CHAT_PLACEHOLDER_KEYWORDS),
        send_button_visible=_contains_any(ocr_text, SEND_BUTTON_KEYWORDS),
        search_box_visible=False,
        modal_type=None,
        last_error_banner=None,
        product_state=merge_anomaly_product_state({}, ocr_text),
    )


def _fallback_state(observation: dict[str, Any]) -> FeishuState:
    ocr_text = observation.get("ocr_text", "")
    if _contains_any(ocr_text, SHELL_SEARCH_KEYWORDS):
        return _shell_search_state(ocr_text)
    if _contains_any(ocr_text, CHAT_SEARCH_PANEL_KEYWORDS):
        return _im_chat_search_panel_state(ocr_text)

    page_descriptor: PageDescriptor | None = None
    if _contains_any(ocr_text, CHAT_PLACEHOLDER_KEYWORDS + MESSAGE_TAB_KEYWORDS):
        page_descriptor = get_page_descriptor("im_chat_main")

    return _im_chat_state(ocr_text, page_descriptor)


def detect_feishu_state(observation: dict[str, Any]) -> FeishuState:
    metadata = normalize_observation(observation)
    if metadata:
        return _state_from_metadata(metadata)
    return _fallback_state(observation)


def detect_im_state(observation: dict[str, Any]) -> FeishuState:
    """Backward-compatible alias kept for early Track B tests."""

    return detect_feishu_state(observation)
