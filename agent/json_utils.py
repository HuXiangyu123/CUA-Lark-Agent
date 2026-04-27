"""Shared helpers for extracting JSON objects from model output."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first valid JSON object from fenced or raw model output."""
    for match in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        data = _try_load_json(match)
        if isinstance(data, dict):
            return data

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                data = _try_load_json(text[start : index + 1])
                if isinstance(data, dict):
                    return data
                break
    return None


def _try_load_json(text: str) -> Any:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None
