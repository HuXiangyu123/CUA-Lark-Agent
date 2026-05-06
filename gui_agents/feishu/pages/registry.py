"""Registry for Feishu page descriptors."""

from __future__ import annotations

from gui_agents.feishu.contracts import PageDescriptor

from .calendar_date_picker import CALENDAR_DATE_PICKER_DESCRIPTOR
from .calendar_event_modal import CALENDAR_EVENT_MODAL_DESCRIPTOR
from .calendar_home import CALENDAR_HOME_DESCRIPTOR
from .calendar_quick_add_modal import CALENDAR_QUICK_ADD_MODAL_DESCRIPTOR
from .base_browser_table import BASE_BROWSER_TABLE_DESCRIPTOR
from .base_home import BASE_HOME_DESCRIPTOR
from .base_new_menu import BASE_NEW_MENU_DESCRIPTOR
from .base_secondary_surfaces import (
    BASE_APP_MARKET_DESCRIPTOR,
    BASE_AUTOMATION_DESCRIPTOR,
    BASE_DASHBOARD_DESCRIPTOR,
    BASE_SHARE_PANEL_DESCRIPTOR,
)
from .base_template_gallery import BASE_TEMPLATE_GALLERY_DESCRIPTOR
from .docs_browser_editor import DOCS_BROWSER_EDITOR_DESCRIPTOR
from .docs_home import DOCS_HOME_DESCRIPTOR
from .docs_new_dropdown import DOCS_NEW_DROPDOWN_DESCRIPTOR
from .docs_template_gallery import DOCS_TEMPLATE_GALLERY_DESCRIPTOR
from .feishu_shell_search import FEISHU_SHELL_SEARCH_DESCRIPTOR
from .im_chat_main import IM_CHAT_MAIN_DESCRIPTOR
from .im_chat_search_panel import IM_CHAT_SEARCH_PANEL_DESCRIPTOR
from .vc_home import VC_HOME_DESCRIPTOR
from .vc_invite_dialog import VC_INVITE_DIALOG_DESCRIPTOR
from .vc_join_preview import VC_JOIN_PREVIEW_DESCRIPTOR
from .vc_meeting_active import VC_MEETING_ACTIVE_DESCRIPTOR
from .vc_start_preview import VC_START_PREVIEW_DESCRIPTOR


_DESCRIPTORS = (
    CALENDAR_HOME_DESCRIPTOR,
    CALENDAR_EVENT_MODAL_DESCRIPTOR,
    CALENDAR_QUICK_ADD_MODAL_DESCRIPTOR,
    CALENDAR_DATE_PICKER_DESCRIPTOR,
    BASE_HOME_DESCRIPTOR,
    BASE_NEW_MENU_DESCRIPTOR,
    BASE_TEMPLATE_GALLERY_DESCRIPTOR,
    BASE_BROWSER_TABLE_DESCRIPTOR,
    BASE_SHARE_PANEL_DESCRIPTOR,
    BASE_DASHBOARD_DESCRIPTOR,
    BASE_AUTOMATION_DESCRIPTOR,
    BASE_APP_MARKET_DESCRIPTOR,
    DOCS_HOME_DESCRIPTOR,
    DOCS_NEW_DROPDOWN_DESCRIPTOR,
    DOCS_TEMPLATE_GALLERY_DESCRIPTOR,
    DOCS_BROWSER_EDITOR_DESCRIPTOR,
    FEISHU_SHELL_SEARCH_DESCRIPTOR,
    IM_CHAT_MAIN_DESCRIPTOR,
    IM_CHAT_SEARCH_PANEL_DESCRIPTOR,
    VC_HOME_DESCRIPTOR,
    VC_START_PREVIEW_DESCRIPTOR,
    VC_MEETING_ACTIVE_DESCRIPTOR,
    VC_JOIN_PREVIEW_DESCRIPTOR,
    VC_INVITE_DIALOG_DESCRIPTOR,
)


PAGE_REGISTRY: dict[str, PageDescriptor] = {
    descriptor["page_id"]: descriptor for descriptor in _DESCRIPTORS
}


def get_page_ids() -> list[str]:
    return list(PAGE_REGISTRY)


def get_page_descriptor(page_id: str) -> PageDescriptor | None:
    return PAGE_REGISTRY.get(page_id)
