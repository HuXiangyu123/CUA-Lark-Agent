"""Shared helpers for extracting JSON objects from model output."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first valid JSON object from fenced or raw model output."""
    for match in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE):
        data = _try_load_json(match)
        if isinstance(data, dict):
            return data

    for start, end in _iter_json_object_spans(text):
        data = _try_load_json(text[start:end])
        if isinstance(data, dict):
            return data
    return None


def _try_load_json(text: str) -> Any:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _iter_json_object_spans(text: str) -> Iterator[tuple[int, int]]:
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                yield start, index + 1
                start = None
