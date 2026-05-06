"""Feishu Calendar time-slot quick-add modal descriptor."""

from __future__ import annotations

from gui_agents.feishu.contracts import PageDescriptor


CALENDAR_QUICK_ADD_MODAL_DESCRIPTOR: PageDescriptor = {
    "page_id": "calendar_quick_add_modal",
    "page_type": "calendar_quick_add_modal",
    "display_name": "Feishu Calendar Quick Add Modal",
    "layout_hints": {
        "surface": "feishu_desktop_calendar",
        "container": "time_slot_quick_add_popover",
        "origin": "calendar_week_grid_time_slot",
    },
    "key_regions": {
        "title_input": {
            "role": "event_title_input",
            "visible_placeholder": "添加主题",
        },
        "attendee_input": {
            "role": "attendee_input",
            "visible_placeholder": "添加联系人、群或邮箱",
        },
        "time_range": {
            "role": "event_time_range",
            "description": "selected time slot editor",
        },
        "save_button": {
            "role": "save_event_button",
            "visible_text": "保存",
        },
    },
    "text_anchors": [
        "添加日程",
        "添加主题",
        "添加联系人、群或邮箱",
        "保存",
    ],
    "ui_version_tag": "feishu-desktop-calendar",
}
