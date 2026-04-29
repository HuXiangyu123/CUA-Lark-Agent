"""Windows DPI awareness helpers for GUI coordinate consistency."""

from __future__ import annotations

import sys


_DPI_AWARENESS_ATTEMPTED = False


def ensure_windows_dpi_awareness() -> None:
    """Put Windows GUI APIs on the same physical-pixel coordinate system.

    Windows display scaling can otherwise make screenshot pixels, window
    bounds, and pyautogui mouse coordinates disagree with each other.
    """
    global _DPI_AWARENESS_ATTEMPTED
    if _DPI_AWARENESS_ATTEMPTED or sys.platform != "win32":
        return
    _DPI_AWARENESS_ATTEMPTED = True

    try:
        import ctypes
    except ImportError:
        return

    try:
        awareness_contexts = (
            -4,  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            -3,  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE
        )
        for context in awareness_contexts:
            try:
                if ctypes.windll.user32.SetProcessDpiAwarenessContext(context):
                    return
            except Exception:
                continue

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return
        except Exception:
            pass

        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        return
