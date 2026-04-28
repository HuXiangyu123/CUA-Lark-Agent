"""Window activation, bounds lookup, and coordinate translation."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, replace

from agent.gui.capture import ScreenshotArtifact
from agent.gui.schema import GuiAction


@dataclass
class WindowInfo:
    app_name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def region(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height


class MacOSWindowManager:
    """Manage window activation and geometry for a target app.

    The original project was macOS-first and used AppleScript. On Windows and
    Linux we use PyGetWindow/PyAutoGUI's window helpers so the same runner can
    be used for local demos.
    """

    def activate(self, app_name: str) -> None:
        if sys.platform != "darwin":
            window = self._find_window(app_name)
            was_minimized = bool(getattr(window, "isMinimized", False))
            try:
                if was_minimized:
                    window.restore()
                    time.sleep(0.25)
                    window = self._find_window(app_name)
                window.activate()
                time.sleep(0.2)
                if was_minimized and sys.platform == "win32":
                    self._click_window_titlebar(window)
            except Exception as exc:
                # PyGetWindow on Windows can raise an exception even when the
                # underlying Win32 call reports success. Window-relative
                # capture can still proceed as long as bounds are available.
                if sys.platform == "win32" and "Error code from Windows: 0" in str(exc):
                    if was_minimized:
                        try:
                            window = self._find_window(app_name)
                            self._click_window_titlebar(window)
                        except Exception:
                            pass
                    time.sleep(0.2)
                    return
                raise RuntimeError(f"failed to activate window for {app_name!r}: {exc}") from exc
            return
        subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'], check=True)

    def frontmost_app(self) -> str:
        if sys.platform != "darwin":
            try:
                import pygetwindow as gw  # type: ignore
            except ImportError as exc:
                raise RuntimeError("pygetwindow is required for non-macOS window lookup") from exc
            window = gw.getActiveWindow()
            return window.title if window else ""
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def get_window(self, app_name: str) -> WindowInfo:
        if sys.platform != "darwin":
            window = self._find_window(app_name)
            return WindowInfo(
                app_name=app_name,
                x=int(window.left),
                y=int(window.top),
                width=int(window.width),
                height=int(window.height),
            )
        result = subprocess.run(
            [
                "osascript",
                "-e",
                _list_windows_script(app_name),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        windows = _parse_window_list(result.stdout)
        if not windows:
            raise RuntimeError(f"no usable windows found for {app_name!r}: {result.stdout.strip()!r}")
        x, y, width, height = _select_main_window(windows)
        return WindowInfo(app_name=app_name, x=x, y=y, width=width, height=height)

    def activate_and_get_window(self, app_name: str) -> WindowInfo:
        self.activate(app_name)
        return self.get_window(app_name)

    def _find_window(self, app_name: str):
        try:
            import pygetwindow as gw  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pygetwindow is required for non-macOS window lookup") from exc

        candidates = _window_title_candidates(app_name)
        windows = [
            window
            for window in gw.getAllWindows()
            if _window_matches_app_title(getattr(window, "title", "") or "", candidates)
        ]
        if not windows:
            all_titles = [w.title for w in gw.getAllWindows() if getattr(w, "title", "")]
            preview = ", ".join(all_titles[:10])
            raise RuntimeError(
                f"no usable windows found for {app_name!r}. "
                f"Open the target app first or set GUI_TARGET_APP to part of its window title. "
                f"Visible windows: {preview}"
            )
        usable = [
            w for w in windows
            if int(w.width) > 0
            and int(w.height) > 0
            and int(w.left) > -10000
            and int(w.top) > -10000
        ]
        if usable:
            return max(usable, key=lambda item: (int(item.width) * int(item.height), int(item.width), int(item.height)))

        restorable = [w for w in windows if getattr(w, "isMinimized", False)]
        if restorable:
            return max(restorable, key=lambda item: (int(item.width), int(item.height)))

        raise RuntimeError(f"windows found for {app_name!r}, but none have usable bounds")

    def _click_window_titlebar(self, window) -> None:
        try:
            import pyautogui  # type: ignore
        except ImportError:
            return

        x, y = _titlebar_click_point(
            int(getattr(window, "left", 0)),
            int(getattr(window, "top", 0)),
            int(getattr(window, "width", 0)),
            int(getattr(window, "height", 0)),
        )
        pyautogui.moveTo(x, y, duration=0.12)
        pyautogui.click(x, y)
        time.sleep(0.15)


def translate_action_to_screen(action: GuiAction, window: WindowInfo) -> GuiAction:
    """Translate screenshot-local coordinates into absolute screen coordinates."""
    if action.type in {"type", "hotkey", "wait"}:
        return action

    translated = replace(action)
    if translated.x is not None:
        translated.x += window.x
    if translated.y is not None:
        translated.y += window.y
    if translated.end_x is not None:
        translated.end_x += window.x
    if translated.end_y is not None:
        translated.end_y += window.y
    return translated


def translate_action_from_image_to_screen(action: GuiAction, observation: ScreenshotArtifact) -> GuiAction:
    """Translate image-pixel coordinates into absolute screen coordinates."""
    if action.type in {"type", "hotkey", "wait"}:
        return action

    translated = replace(action)
    if translated.x is not None:
        translated.x = observation.origin_x + int(round(translated.x / max(observation.scale_x, 1e-6)))
    if translated.y is not None:
        translated.y = observation.origin_y + int(round(translated.y / max(observation.scale_y, 1e-6)))
    if translated.end_x is not None:
        translated.end_x = observation.origin_x + int(round(translated.end_x / max(observation.scale_x, 1e-6)))
    if translated.end_y is not None:
        translated.end_y = observation.origin_y + int(round(translated.end_y / max(observation.scale_y, 1e-6)))
    return translated


def _parse_bounds(output: str) -> tuple[int, int, int, int]:
    parts = [int(part.strip()) for part in output.strip().split(",")]
    if len(parts) != 4:
        raise RuntimeError(f"unexpected bounds output: {output.strip()!r}")
    return parts[0], parts[1], parts[2], parts[3]


def _list_windows_script(app_name: str) -> str:
    escaped = app_name.replace('"', '\\"')
    return f'''
tell application "System Events"
  tell application process "{escaped}"
    set outputText to ""
    repeat with w in every window
      try
        set {{px, py}} to position of w
        set {{sw, sh}} to size of w
        set outputText to outputText & (px as text) & "," & (py as text) & "," & (sw as text) & "," & (sh as text) & linefeed
      end try
    end repeat
    return outputText
  end tell
end tell
'''.strip()


def _parse_window_list(output: str) -> list[tuple[int, int, int, int]]:
    windows: list[tuple[int, int, int, int]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            windows.append(_parse_bounds(line))
        except (RuntimeError, ValueError):
            continue
    return windows


def _select_main_window(windows: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    valid = [window for window in windows if window[2] > 0 and window[3] > 0]
    if not valid:
        raise RuntimeError(f"no valid windows in: {windows!r}")
    return max(valid, key=lambda item: (item[2] * item[3], item[2], item[3], -item[1], -item[0]))


def _titlebar_click_point(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    return x + max(1, width // 2), y + min(max(12, height // 30), 32)


def _window_title_candidates(app_name: str) -> list[str]:
    candidates = [app_name]
    lowered = app_name.lower()
    if lowered in {"feishu", "lark"}:
        candidates.extend(["飞书"])
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _window_matches_app_title(title: str, candidates: list[str]) -> bool:
    normalized_title = title.strip().lower()
    if not normalized_title:
        return False

    for candidate in candidates:
        normalized_candidate = candidate.strip().lower()
        if not normalized_candidate:
            continue
        if normalized_candidate in {"feishu", "lark"}:
            if normalized_title in {"feishu", "lark", "飞书"}:
                return True
            continue
        if normalized_candidate in normalized_title:
            return True
    return False
