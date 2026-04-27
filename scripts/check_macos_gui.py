#!/usr/bin/env python3
"""Preflight checks for macOS GUI automation permissions."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    report = {
        "platform": sys.platform,
        "checks": [],
    }

    if sys.platform != "darwin":
        report["checks"].append(
            {
                "name": "platform",
                "ok": False,
                "detail": "This preflight only supports macOS.",
            }
        )
        _print_report(report)
        return 1

    report["checks"].append(_check_binary("screencapture"))
    report["checks"].append(_check_binary("osascript"))
    report["checks"].append(_check_screen_recording())
    report["checks"].append(_check_accessibility())
    report["checks"].append(_check_imports())

    _print_report(report)
    return 0 if all(item["ok"] for item in report["checks"]) else 1


def _check_binary(name: str) -> dict:
    path = shutil.which(name)
    return {
        "name": f"binary:{name}",
        "ok": bool(path),
        "detail": path or f"{name} not found in PATH",
    }


def _check_screen_recording() -> dict:
    try:
        from Quartz import CGPreflightScreenCaptureAccess  # type: ignore
    except Exception as exc:
        return {
            "name": "screen_recording_api",
            "ok": False,
            "detail": f"Quartz import failed: {exc}",
        }

    permission_ok = bool(CGPreflightScreenCaptureAccess())
    detail = "Permission granted" if permission_ok else "Permission missing"

    capture_ok = False
    capture_detail = "Skipped because permission is missing"
    if permission_ok:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                image_path = Path(tmpdir) / "preflight.png"
                subprocess.run(["screencapture", "-x", str(image_path)], check=True)
                capture_ok = image_path.exists() and image_path.stat().st_size > 0
                capture_detail = f"Captured {image_path.stat().st_size} bytes" if capture_ok else "Capture output was empty"
        except Exception as exc:
            capture_detail = str(exc)

    return {
        "name": "screen_recording",
        "ok": permission_ok and capture_ok,
        "detail": f"{detail}; {capture_detail}",
    }


def _check_accessibility() -> dict:
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to return UI elements enabled'],
            capture_output=True,
            text=True,
            check=True,
        )
        enabled = result.stdout.strip().lower() == "true"
        return {
            "name": "accessibility",
            "ok": enabled,
            "detail": result.stdout.strip() or "No output",
        }
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        return {
            "name": "accessibility",
            "ok": False,
            "detail": detail,
        }


def _check_imports() -> dict:
    try:
        import openai  # noqa: F401
        import pyautogui  # noqa: F401
    except Exception as exc:
        return {
            "name": "python_imports",
            "ok": False,
            "detail": str(exc),
        }

    return {
        "name": "python_imports",
        "ok": True,
        "detail": "openai and pyautogui imported successfully",
    }


def _print_report(report: dict) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
