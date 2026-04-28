"""Screen capture utilities for GUI execution."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScreenshotArtifact:
    path: Path
    width: int
    height: int
    origin_x: int = 0
    origin_y: int = 0
    screen_width: int = 0
    screen_height: int = 0
    scale_x: float = 1.0
    scale_y: float = 1.0


class ScreenCapture:
    """Capture full-screen screenshots for the GUI planner."""

    def capture(
        self,
        output_dir: Path,
        name: str,
        region: tuple[int, int, int, int] | None = None,
    ) -> ScreenshotArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{name}.png"

        if sys.platform == "darwin":
            command = ["screencapture", "-x"]
            if region is not None:
                x, y, width, height = region
                command.extend(["-R", f"{x},{y},{width},{height}"])
            command.append(str(path))
            subprocess.run(command, check=True)
            _maybe_resize_capture(path)
            pixel_width, pixel_height = _read_image_size(path)
            if region is not None:
                x, y, width, height = region
                return ScreenshotArtifact(
                    path=path,
                    width=pixel_width,
                    height=pixel_height,
                    origin_x=x,
                    origin_y=y,
                    screen_width=width,
                    screen_height=height,
                    scale_x=pixel_width / max(width, 1),
                    scale_y=pixel_height / max(height, 1),
                )
            screen_width, screen_height = _read_macos_screen_size()
            return ScreenshotArtifact(
                path=path,
                width=pixel_width,
                height=pixel_height,
                origin_x=0,
                origin_y=0,
                screen_width=screen_width,
                screen_height=screen_height,
                scale_x=pixel_width / max(screen_width, 1),
                scale_y=pixel_height / max(screen_height, 1),
            )

        if sys.platform == "win32":
            image, virtual_origin, virtual_size = _grab_windows_desktop()
            if region is not None:
                x, y, width, height = region
                origin_x, origin_y = virtual_origin
                image = image.crop((x - origin_x, y - origin_y, x - origin_x + width, y - origin_y + height))
            image.save(path)
            pixel_width, pixel_height = _read_image_size(path)
            if region is not None:
                x, y, width, height = region
                return ScreenshotArtifact(
                    path=path,
                    width=pixel_width,
                    height=pixel_height,
                    origin_x=x,
                    origin_y=y,
                    screen_width=width,
                    screen_height=height,
                    scale_x=pixel_width / max(width, 1),
                    scale_y=pixel_height / max(height, 1),
                )
            return ScreenshotArtifact(
                path=path,
                width=pixel_width,
                height=pixel_height,
                origin_x=virtual_origin[0],
                origin_y=virtual_origin[1],
                screen_width=virtual_size[0],
                screen_height=virtual_size[1],
                scale_x=pixel_width / max(virtual_size[0], 1),
                scale_y=pixel_height / max(virtual_size[1], 1),
            )

        pyautogui = _load_pyautogui()
        image = pyautogui.screenshot()
        if region is not None:
            x, y, width, height = region
            image = image.crop((x, y, x + width, y + height))
        image.save(path)
        if region is not None:
            x, y, width, height = region
            return ScreenshotArtifact(
                path=path,
                width=width,
                height=height,
                origin_x=x,
                origin_y=y,
                screen_width=width,
                screen_height=height,
                scale_x=1.0,
                scale_y=1.0,
            )
        size = pyautogui.size()
        return ScreenshotArtifact(
            path=path,
            width=size.width,
            height=size.height,
            origin_x=0,
            origin_y=0,
            screen_width=size.width,
            screen_height=size.height,
            scale_x=1.0,
            scale_y=1.0,
        )


def _read_macos_screen_size() -> tuple[int, int]:
    script = 'tell application "Finder" to get bounds of window of desktop'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    parts = [int(part.strip()) for part in result.stdout.strip().split(",")]
    if len(parts) != 4:
        raise RuntimeError(f"unexpected desktop bounds: {result.stdout.strip()}")
    return parts[2], parts[3]


def _read_image_size(path: Path) -> tuple[int, int]:
    if sys.platform == "darwin":
        result = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        pixel_width = None
        pixel_height = None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("pixelWidth:"):
                pixel_width = int(line.split(":", 1)[1].strip())
            elif line.startswith("pixelHeight:"):
                pixel_height = int(line.split(":", 1)[1].strip())
        if pixel_width is None or pixel_height is None:
            raise RuntimeError(f"failed to parse image size from sips output: {result.stdout}")
        return pixel_width, pixel_height

    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Pillow is required to inspect screenshot size") from exc

    with Image.open(path) as image:
        return image.size


def _load_pyautogui():
    try:
        import pyautogui  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyautogui is required for non-macOS screen capture") from exc
    return pyautogui


def _grab_windows_desktop():
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Pillow ImageGrab is required for Windows screen capture") from exc

    origin_x, origin_y, width, height = _windows_virtual_screen_bounds()
    return ImageGrab.grab(all_screens=True), (origin_x, origin_y), (width, height)


def _windows_virtual_screen_bounds() -> tuple[int, int, int, int]:
    try:
        import ctypes
    except ImportError:
        pyautogui = _load_pyautogui()
        size = pyautogui.size()
        return 0, 0, int(size.width), int(size.height)

    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(76)),  # SM_XVIRTUALSCREEN
        int(user32.GetSystemMetrics(77)),  # SM_YVIRTUALSCREEN
        int(user32.GetSystemMetrics(78)),  # SM_CXVIRTUALSCREEN
        int(user32.GetSystemMetrics(79)),  # SM_CYVIRTUALSCREEN
    )


def _maybe_resize_capture(path: Path) -> None:
    max_dimension = _capture_resize_limit()
    if sys.platform != "darwin" or max_dimension <= 0:
        return

    width, height = _read_image_size(path)
    if max(width, height) <= max_dimension:
        return

    subprocess.run(
        ["sips", "-Z", str(max_dimension), str(path)],
        capture_output=True,
        text=True,
        check=True,
    )


def _capture_resize_limit() -> int:
    raw = (
        os.environ.get("GUI_SCREENSHOT_MAX_DIMENSION", "").strip()
        or os.environ.get("CUA_SCREENSHOT_MAX_DIMENSION", "").strip()
        or "1440"
    )
    try:
        return max(0, int(raw))
    except ValueError:
        return 1440
