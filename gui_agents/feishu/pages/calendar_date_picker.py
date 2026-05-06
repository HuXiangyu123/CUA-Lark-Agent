"""Feishu Calendar date picker descriptor."""

from __future__ import annotations

from gui_agents.feishu.contracts import PageDescriptor


CALENDAR_DATE_PICKER_DESCRIPTOR: PageDescriptor = {
    "page_id": "calendar_date_picker",
    "page_type": "calendar_date_picker",
    "display_name": "Feishu Calendar Date Picker",
    "layout_hints": {
        "surface": "feishu_desktop_calendar",
        "container": "header_date_picker_popover",
        "origin": "calendar_header_date_control",
    },
    "key_regions": {
        "date_header_control": {
            "role": "calendar_header_date_control",
            "description": "date label button that opens the date picker",
        },
        "month_picker": {
            "role": "month_calendar_picker",
            "description": "month grid for choosing the visible calendar date",
        },
        "today_shortcut": {
            "role": "today_shortcut",
            "visible_text": "今天",
        },
    },
    "text_anchors": [
        "今天",
        "2026 年 5月",
    ],
    "ui_version_tag": "feishu-desktop-calendar",
}
