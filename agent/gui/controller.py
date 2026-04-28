"""GUI action executor backed by pyautogui."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

from agent.gui.schema import GuiAction


@dataclass
class ActionExecutionResult:
    ok: bool
    action_type: str
    detail: str
    duration_ms: int
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action_type": self.action_type,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
            "dry_run": self.dry_run,
        }


class GuiController:
    """Perform concrete mouse and keyboard actions."""

    def __init__(self, dry_run: bool = False, pause_seconds: float = 0.5):
        self.dry_run = dry_run
        self.pause_seconds = pause_seconds
        self._pyautogui = None

    def execute(self, action: GuiAction) -> ActionExecutionResult:
        started = time.perf_counter()
        if self.dry_run:
            return self._result(action, started, f"dry-run: {action.type}")

        pyautogui = self._pg()

        if action.type == "click":
            pyautogui.click(action.x, action.y)
        elif action.type == "double_click":
            pyautogui.doubleClick(action.x, action.y)
        elif action.type == "right_click":
            pyautogui.click(action.x, action.y, button="right")
        elif action.type == "drag":
            pyautogui.moveTo(action.x, action.y)
            pyautogui.dragTo(action.end_x, action.end_y, duration=0.25, button="left")
        elif action.type == "scroll":
            if action.x is not None and action.y is not None:
                pyautogui.moveTo(action.x, action.y)
            pyautogui.scroll(action.scroll_amount)
        elif action.type == "type":
            self._type_text(pyautogui, action.text or "")
        elif action.type == "hotkey":
            keys = action.keys or []
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
        elif action.type == "wait":
            time.sleep((action.duration_ms or 1000) / 1000)
        else:
            raise RuntimeError(f"unsupported action: {action.type}")

        return self._result(action, started, f"executed: {action.type}")

    def _result(self, action: GuiAction, started: float, detail: str) -> ActionExecutionResult:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ActionExecutionResult(
            ok=True,
            action_type=action.type,
            detail=detail,
            duration_ms=duration_ms,
            dry_run=self.dry_run,
        )

    def _pg(self):
        if self._pyautogui is None:
            try:
                import pyautogui  # type: ignore
            except ImportError as exc:
                raise RuntimeError("pyautogui is required for GUI execution") from exc
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = self.pause_seconds
            self._pyautogui = pyautogui
        return self._pyautogui

    def _type_text(self, pyautogui, text: str) -> None:
        if not text:
            return
        if sys.platform == "darwin":
            self._paste_text_mac(pyautogui, text)
            return
        self._paste_text_cross_platform(pyautogui, text)

    def _paste_text_mac(self, pyautogui, text: str) -> None:
        previous_clipboard = subprocess.run(
            ["pbpaste"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        time.sleep(max(self.pause_seconds, 0.08))
        pyautogui.hotkey("command", "v")
        time.sleep(max(self.pause_seconds, 0.08))
        subprocess.run(["pbcopy"], input=previous_clipboard, text=True, check=False)

    def _paste_text_cross_platform(self, pyautogui, text: str) -> None:
        try:
            import pyperclip  # type: ignore
        except ImportError:
            pyautogui.write(text, interval=0.02)
            return

        previous_clipboard = ""
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = ""

        pyperclip.copy(text)
        time.sleep(max(self.pause_seconds, 0.08))
        if sys.platform == "win32":
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.hotkey("ctrl", "v")
        time.sleep(max(self.pause_seconds, 0.08))
        try:
            pyperclip.copy(previous_clipboard)
        except Exception:
            pass
