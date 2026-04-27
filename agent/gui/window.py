"""macOS window activation, bounds lookup, and coordinate translation."""

from __future__ import annotations

import subprocess
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
    """Manage window activation and geometry for a target app on macOS."""

    def activate(self, app_name: str) -> None:
        subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'], check=True)

    def frontmost_app(self) -> str:
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
