"""Routing helpers for API and GUI execution modes."""

from __future__ import annotations

from enum import Enum


class RouteMode(str, Enum):
    AUTO = "auto"
    API = "api"
    GUI = "gui"


_GUI_HINTS = (
    "gui",
    "click",
    "double click",
    "right click",
    "drag",
    "scroll",
    "hotkey",
    "desktop",
    "client",
    "button",
    "dialog",
    "popup",
    "窗口",
    "桌面",
    "客户端",
    "点击",
    "双击",
    "右键",
    "拖拽",
    "滚动",
    "输入",
    "快捷键",
    "界面",
    "按钮",
    "弹窗",
)

_API_HINTS = (
    "lark-cli",
    "api ",
    "chat_id",
    "open_id",
    "doc token",
    "calendar id",
    "命令行",
    "接口",
)

_MODE_PREFIXES = {
    "/api": RouteMode.API,
    "/gui": RouteMode.GUI,
    "/auto": RouteMode.AUTO,
}


def resolve_route(user_input: str, requested_mode: RouteMode) -> tuple[RouteMode, str]:
    """Resolve the effective route and strip optional mode directives."""
    stripped = user_input.strip()

    for prefix, mode in _MODE_PREFIXES.items():
        if stripped.lower().startswith(prefix):
            remainder = stripped[len(prefix) :].strip()
            return mode, remainder

    if requested_mode != RouteMode.AUTO:
        return requested_mode, stripped

    lowered = stripped.lower()
    gui_score = sum(1 for hint in _GUI_HINTS if hint in lowered or hint in stripped)
    api_score = sum(1 for hint in _API_HINTS if hint in lowered or hint in stripped)

    if gui_score > 0 and gui_score >= api_score:
        return RouteMode.GUI, stripped
    return RouteMode.API, stripped
