"""Metadata-first state detector for Feishu Docs Track B."""

from __future__ import annotations

from typing import Any

from gui_agents.feishu.contracts import FeishuState
from gui_agents.feishu.detectors.anomaly import merge_anomaly_product_state
from gui_agents.feishu.observation import normalize_observation
from gui_agents.feishu.pages.registry import get_page_descriptor


DOCS_HOME_KEYWORDS = ("云文档", "主页", "新建", "上传", "模板库")
DOCS_NEW_DROPDOWN_KEYWORDS = ("新建", "文档", "多维表格", "文件夹")
DOCS_TEMPLATE_GALLERY_KEYWORDS = ("搜索模板", "新建空白文档", "为你推荐")
DOCS_BROWSER_EDITOR_KEYWORDS = ("飞书云文档", "请输入标题", "快速插入内容", "分享")
DOCS_SHARE_DIALOG_KEYWORDS = ("分享链接", "邀请协作", "复制链接", "权限设置")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _state_from_metadata(metadata: dict[str, Any]) -> FeishuState:
    expected = metadata.get("expected_state", {})
    product_state = dict(metadata.get("product_state", {}))
    return FeishuState(
        page_type=expected.get("page_type") or metadata.get("page_type", "unknown"),
        product=expected.get("product") or metadata.get("product", "docs"),
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

    share_dialog_keywords_matched = sum(
        1 for kw in DOCS_SHARE_DIALOG_KEYWORDS if kw in ocr_text
    )
    if share_dialog_keywords_matched >= 2:
        page_id = "docs_browser_editor"
        product_state = {
            "editor_ready": True,
            "share_dialog_visible": True,
        }
    elif _contains_any(ocr_text, DOCS_BROWSER_EDITOR_KEYWORDS):
        page_id = "docs_browser_editor"
        product_state = {"editor_ready": True}
    elif _contains_any(ocr_text, DOCS_TEMPLATE_GALLERY_KEYWORDS):
        page_id = "docs_template_gallery"
        product_state = {"blank_doc_card_visible": "新建空白文档" in ocr_text}
    elif _contains_any(ocr_text, DOCS_NEW_DROPDOWN_KEYWORDS):
        page_id = "docs_new_dropdown"
        product_state = {"document_option_visible": "文档" in ocr_text}
    elif _contains_any(ocr_text, DOCS_HOME_KEYWORDS):
        page_id = "docs_home"
        product_state = {
            "docs_home_visible": True,
            "new_card_visible": "新建" in ocr_text,
            "document_list_visible": "最近访问" in ocr_text or "所有者" in ocr_text,
        }
    product_state = merge_anomaly_product_state(product_state, ocr_text)

    descriptor = get_page_descriptor(page_id) if page_id else None
    return FeishuState(
        page_type=descriptor["page_type"] if descriptor else "unknown",
        product="docs" if descriptor else "unknown",
        chat_name=None,
        message_input_visible=False,
        send_button_visible=False,
        search_box_visible=page_id in {"docs_home", "docs_template_gallery"},
        modal_type=None,
        last_error_banner=None,
        product_state=product_state,
    )


def detect_docs_state(observation: dict[str, Any]) -> FeishuState:
    metadata = normalize_observation(observation)
    if metadata:
        return _state_from_metadata(metadata)
    return _fallback_state(observation)
