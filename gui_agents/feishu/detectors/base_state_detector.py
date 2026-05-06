"""Metadata-first state detector for Feishu Base."""

from __future__ import annotations

from typing import Any

from gui_agents.feishu.contracts import FeishuState
from gui_agents.feishu.detectors.anomaly import merge_anomaly_product_state
from gui_agents.feishu.observation import normalize_observation
from gui_agents.feishu.pages.registry import get_page_descriptor


BASE_HOME_KEYWORDS = ("飞书多维表格", "多维表格", "全部多维表格", "应用市场")
BASE_NEW_MENU_KEYWORDS = ("新建多维表格", "新建应用", "新建收集表", "导入 Excel")
BASE_TEMPLATE_KEYWORDS = ("模板中心", "今天你想搭建什么", "新建多维表格")
BASE_EDITOR_KEYWORDS = ("未命名多维表格", "数据表", "添加记录", "自动化")
BASE_SHARE_KEYWORDS = ("链接分享", "邀请", "权限")
BASE_AUTOMATION_KEYWORDS = ("自动化", "创建自动化流程", "工作流")
BASE_DASHBOARD_KEYWORDS = ("仪表盘", "添加组件")
BASE_APP_MARKET_KEYWORDS = ("热门应用", "应用市场", "添加组件")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _state_from_metadata(metadata: dict[str, Any]) -> FeishuState:
    expected = metadata.get("expected_state", {})
    product_state = dict(metadata.get("product_state", {}))
    return FeishuState(
        page_type=expected.get("page_type") or metadata.get("page_type", "unknown"),
        product=expected.get("product") or metadata.get("product", "base"),
        chat_name=None,
        message_input_visible=bool(expected.get("message_input_visible", False)),
        send_button_visible=bool(expected.get("send_button_visible", False)),
        search_box_visible=bool(expected.get("search_box_visible", False)),
        modal_type=expected.get("modal_type"),
        last_error_banner=expected.get("last_error_banner"),
        product_state=product_state,
    )


def _fallback_page_id(ocr_text: str) -> str | None:
    if _contains_any(ocr_text, BASE_SHARE_KEYWORDS):
        return "base_share_panel"
    if _contains_any(ocr_text, BASE_AUTOMATION_KEYWORDS):
        return "base_automation"
    if _contains_any(ocr_text, BASE_DASHBOARD_KEYWORDS):
        return "base_dashboard"
    if _contains_any(ocr_text, BASE_APP_MARKET_KEYWORDS):
        return "base_app_market"
    if _contains_any(ocr_text, BASE_EDITOR_KEYWORDS):
        return "base_browser_table"
    if _contains_any(ocr_text, BASE_TEMPLATE_KEYWORDS):
        return "base_template_gallery"
    if _contains_any(ocr_text, BASE_NEW_MENU_KEYWORDS):
        return "base_new_menu"
    if _contains_any(ocr_text, BASE_HOME_KEYWORDS):
        return "base_home"
    return None


def _fallback_state(observation: dict[str, Any]) -> FeishuState:
    ocr_text = observation.get("ocr_text", "")
    page_id = _fallback_page_id(ocr_text)
    descriptor = get_page_descriptor(page_id) if page_id else None

    product_state: dict[str, Any] = {}
    if page_id == "base_home":
        product_state = {
            "base_home_visible": True,
            "new_button_visible": "新建" in ocr_text,
        }
    elif page_id == "base_new_menu":
        product_state = {
            "new_menu_visible": True,
            "new_base_table_option_visible": "新建多维表格" in ocr_text,
        }
    elif page_id == "base_template_gallery":
        product_state = {
            "template_gallery_visible": True,
            "blank_base_table_card_visible": "新建多维表格" in ocr_text,
        }
    elif page_id == "base_browser_table":
        product_state = {
            "base_editor_ready": True,
            "grid_visible": "数据表" in ocr_text or "添加记录" in ocr_text,
        }
    elif page_id:
        product_state = {"surface_class": "secondary"}
    product_state = merge_anomaly_product_state(product_state, ocr_text)

    return FeishuState(
        page_type=descriptor["page_type"] if descriptor else "unknown",
        product="base" if descriptor else "unknown",
        chat_name=None,
        message_input_visible=False,
        send_button_visible=False,
        search_box_visible=page_id in {"base_home", "base_template_gallery"},
        modal_type=None,
        last_error_banner=None,
        product_state=product_state,
    )


def detect_base_state(observation: dict[str, Any]) -> FeishuState:
    metadata = normalize_observation(observation)
    if metadata:
        return _state_from_metadata(metadata)
    return _fallback_state(observation)
