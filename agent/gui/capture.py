"""Screen capture utilities for GUI execution."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from agent.gui.dpi import ensure_windows_dpi_awareness


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
    action_origin_x: int | None = None
    action_origin_y: int | None = None
    action_scale_x: float | None = None
    action_scale_y: float | None = None


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
            desktop_image_size = image.size
            image_box = None
            if region is not None:
                image_box = _region_to_image_box(region, virtual_origin, virtual_size, desktop_image_size)
                image = image.crop(image_box)
            image.save(path)
            pixel_width, pixel_height = _read_image_size(path)
            if region is not None:
                x, y, width, height = region
                action_origin, action_scale = _windows_action_mapping_for_region(
                    region=region,
                    virtual_origin=virtual_origin,
                    virtual_size=virtual_size,
                    desktop_image_size=desktop_image_size,
                    crop_box=image_box,
                )
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
                    action_origin_x=action_origin[0],
                    action_origin_y=action_origin[1],
                    action_scale_x=action_scale[0],
                    action_scale_y=action_scale[1],
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
    ensure_windows_dpi_awareness()
    try:
        import pyautogui  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyautogui is required for non-macOS screen capture") from exc
    return pyautogui


def _grab_windows_desktop():
    ensure_windows_dpi_awareness()
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Pillow ImageGrab is required for Windows screen capture") from exc

    origin_x, origin_y, width, height = _windows_virtual_screen_bounds()
    return ImageGrab.grab(all_screens=True), (origin_x, origin_y), (width, height)


def _windows_virtual_screen_bounds() -> tuple[int, int, int, int]:
    ensure_windows_dpi_awareness()
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


def _region_to_image_box(
    region: tuple[int, int, int, int],
    virtual_origin: tuple[int, int],
    virtual_size: tuple[int, int],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Convert a Windows logical screen region to ImageGrab pixel coordinates.

    On high-DPI Windows displays, window APIs may report logical coordinates
    while ImageGrab returns physical pixels. Mapping through the virtual screen
    dimensions keeps single-screen laptops, mixed-DPI monitors, and negative
    monitor origins on the same path.
    """
    x, y, width, height = region
    origin_x, origin_y = virtual_origin
    virtual_width, virtual_height = virtual_size
    image_width, image_height = image_size

    scale_x = image_width / max(virtual_width, 1)
    scale_y = image_height / max(virtual_height, 1)

    left = int(round((x - origin_x) * scale_x))
    top = int(round((y - origin_y) * scale_y))
    right = int(round((x + width - origin_x) * scale_x))
    bottom = int(round((y + height - origin_y) * scale_y))

    left = _clamp(left, 0, max(image_width - 1, 0))
    top = _clamp(top, 0, max(image_height - 1, 0))
    right = _clamp(right, left + 1, image_width)
    bottom = _clamp(bottom, top + 1, image_height)
    return left, top, right, bottom


def _windows_action_mapping_for_region(
    *,
    region: tuple[int, int, int, int],
    virtual_origin: tuple[int, int],
    virtual_size: tuple[int, int],
    desktop_image_size: tuple[int, int],
    crop_box: tuple[int, int, int, int] | None,
) -> tuple[tuple[int, int], tuple[float, float]]:
    """Return the screenshot-local -> pyautogui coordinate mapping.

    On some Windows/DPI setups, pyautogui uses the same logical coordinate
    space as Win32 window bounds. On others it behaves closer to ImageGrab's
    physical pixels. Keep capture scaling for VLM prompts, but choose the
    execution mapping from the runtime mouse coordinate space.
    """
    x, y, width, height = region
    image_width, image_height = desktop_image_size
    virtual_width, virtual_height = virtual_size
    image_scale_x = image_width / max(virtual_width, 1)
    image_scale_y = image_height / max(virtual_height, 1)

    mode = _windows_mouse_coord_mode(virtual_size, desktop_image_size)
    if mode == "physical":
        if crop_box is None:
            crop_box = _region_to_image_box(region, virtual_origin, virtual_size, desktop_image_size)
        left, top, _, _ = crop_box
        physical_virtual_origin_x = int(round(virtual_origin[0] * image_scale_x))
        physical_virtual_origin_y = int(round(virtual_origin[1] * image_scale_y))
        return (physical_virtual_origin_x + left, physical_virtual_origin_y + top), (1.0, 1.0)

    logical_scale_x = (crop_box[2] - crop_box[0]) / max(width, 1) if crop_box else image_scale_x
    logical_scale_y = (crop_box[3] - crop_box[1]) / max(height, 1) if crop_box else image_scale_y
    return (
        (x, y),
        (logical_scale_x, logical_scale_y),
    )


def _windows_mouse_coord_mode(
    virtual_size: tuple[int, int],
    desktop_image_size: tuple[int, int],
) -> str:
    forced = (
        os.environ.get("GUI_MOUSE_COORD_MODE", "").strip().lower()
        or os.environ.get("CUA_MOUSE_COORD_MODE", "").strip().lower()
    )
    if forced in {"logical", "physical"}:
        return forced

    try:
        pyautogui = _load_pyautogui()
        size = pyautogui.size()
        mouse_size = (int(size.width), int(size.height))
    except Exception:
        return "logical"

    physical_distance = _size_distance(mouse_size, desktop_image_size)
    logical_distance = _size_distance(mouse_size, virtual_size)
    return "physical" if physical_distance < logical_distance else "logical"


def _size_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


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
