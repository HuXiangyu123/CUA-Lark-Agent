"""Direct manual GUI actions for low-level capability validation."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from agent.gui.capture import ScreenCapture
from agent.gui.controller import GuiController
from agent.gui.schema import GuiAction
from agent.gui.window import MacOSWindowManager, translate_action_to_screen


def build_action_from_args(args: Namespace) -> GuiAction:
    """Build a validated GuiAction from argparse args."""
    payload: dict[str, object] = {
        "type": args.action_type,
        "target": args.target or "",
        "x": args.x,
        "y": args.y,
        "end_x": args.end_x,
        "end_y": args.end_y,
        "text": args.text,
        "scroll_amount": args.amount,
        "duration_ms": args.duration_ms,
    }
    if args.keys:
        payload["keys"] = [part.strip() for part in args.keys.split(",") if part.strip()]
    return GuiAction.from_dict(payload)


def execute_manual_action(args: Namespace) -> str:
    """Execute a single GUI action and return JSON output."""
    action = build_action_from_args(args)
    screen_action = action
    if getattr(args, "relative_to_app", None):
        window = MacOSWindowManager().activate_and_get_window(args.relative_to_app)
        screen_action = translate_action_to_screen(action, window)
    controller = GuiController(dry_run=args.dry_run, pause_seconds=args.pause)
    result = controller.execute(screen_action)
    response = {
        "action": action.to_dict(),
        "screen_action": screen_action.to_dict(),
        "result": result.to_dict(),
    }
    return json.dumps(response, ensure_ascii=False, indent=2)


def capture_once(output_dir: str, name: str, app_name: str | None = None) -> str:
    """Capture a screenshot and return JSON output."""
    region = None
    if app_name:
        region = MacOSWindowManager().activate_and_get_window(app_name).region
    artifact = ScreenCapture().capture(Path(output_dir), name, region=region)
    response = {
        "path": str(artifact.path),
        "width": artifact.width,
        "height": artifact.height,
        "origin_x": artifact.origin_x,
        "origin_y": artifact.origin_y,
        "screen_width": artifact.screen_width,
        "screen_height": artifact.screen_height,
        "scale_x": artifact.scale_x,
        "scale_y": artifact.scale_y,
    }
    return json.dumps(response, ensure_ascii=False, indent=2)
