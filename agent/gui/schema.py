"""Schema validation for GUI planner responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


_ACTION_TYPES = {
    "click",
    "double_click",
    "right_click",
    "drag",
    "scroll",
    "type",
    "hotkey",
    "wait",
}

_STATUSES = {"continue", "done", "blocked"}


@dataclass
class GuiAction:
    type: str
    target: str = ""
    x: int | None = None
    y: int | None = None
    end_x: int | None = None
    end_y: int | None = None
    text: str | None = None
    keys: list[str] | None = None
    scroll_amount: int | None = None
    duration_ms: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuiAction":
        action_type = str(data.get("type", "")).strip().lower()
        if action_type not in _ACTION_TYPES:
            raise ValueError(f"unsupported action type: {action_type}")

        action = cls(
            type=action_type,
            target=str(data.get("target", "")).strip(),
            x=_optional_int(data.get("x")),
            y=_optional_int(data.get("y")),
            end_x=_optional_int(data.get("end_x")),
            end_y=_optional_int(data.get("end_y")),
            text=_optional_str(data.get("text")),
            keys=_normalize_keys(data.get("keys")),
            scroll_amount=_optional_int(data.get("scroll_amount")),
            duration_ms=_optional_int(data.get("duration_ms")),
        )
        action._validate()
        return action

    def _validate(self) -> None:
        if self.type in {"click", "double_click", "right_click"}:
            _require(self.x is not None and self.y is not None, f"{self.type} requires x and y")
        elif self.type == "drag":
            _require(
                None not in (self.x, self.y, self.end_x, self.end_y),
                "drag requires x, y, end_x and end_y",
            )
        elif self.type == "scroll":
            _require(self.scroll_amount is not None, "scroll requires scroll_amount")
        elif self.type == "type":
            _require(self.text not in (None, ""), "type requires text")
        elif self.type == "hotkey":
            _require(bool(self.keys), "hotkey requires keys")
        elif self.type == "wait":
            if self.duration_ms is None or self.duration_ms <= 0:
                self.duration_ms = 1000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GuiDecision:
    status: str
    stage: str
    current_state: str
    progress_assessment: str
    previous_step_ok: bool | None
    success_criteria: str
    completion_evidence: str = ""
    action: GuiAction | None = None
    done_reason: str = ""
    workflow_steps: list[str] = field(default_factory=list)
    active_step_index: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuiDecision":
        status = str(data.get("status", "")).strip().lower()
        if status not in _STATUSES:
            raise ValueError(f"unsupported status: {status}")

        action_data = data.get("action")
        action = GuiAction.from_dict(action_data) if isinstance(action_data, dict) else None
        workflow_steps = _normalize_workflow_steps(data.get("workflow_steps"))

        decision = cls(
            status=status,
            stage=str(data.get("stage", "")).strip() or _default_stage(status),
            current_state=str(data.get("current_state", "")).strip(),
            progress_assessment=str(data.get("progress_assessment", "")).strip(),
            previous_step_ok=_optional_bool(data.get("previous_step_ok")),
            success_criteria=str(data.get("success_criteria", "")).strip(),
            completion_evidence=str(data.get("completion_evidence", "")).strip(),
            action=action,
            done_reason=str(data.get("done_reason", "")).strip(),
            workflow_steps=workflow_steps,
            active_step_index=_optional_int(data.get("active_step_index")),
        )
        decision._validate()
        return decision

    def _validate(self) -> None:
        _require(bool(self.stage), "stage is required")
        if self.status == "continue":
            _require(self.action is not None, "continue status requires action")
            _require(bool(self.success_criteria), "continue status requires success_criteria")
        if self.workflow_steps and self.active_step_index is None and self.status == "continue":
            self.active_step_index = 0
        if self.active_step_index is not None:
            _require(bool(self.workflow_steps), "active_step_index requires workflow_steps")
            _require(
                0 <= self.active_step_index < len(self.workflow_steps),
                "active_step_index must be inside workflow_steps",
            )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.action is not None:
            data["action"] = self.action.to_dict()
        return data


def _normalize_keys(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("keys must be a list")
    normalized = []
    aliases = {
        "cmd": "command",
        "meta": "command",
        "control": "ctrl",
        "option": "alt",
    }
    for item in value:
        key = str(item).strip().lower()
        if not key:
            continue
        normalized.append(aliases.get(key, key))
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(round(float(value)))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if str(value).lower() in {"true", "1"}:
        return True
    if str(value).lower() in {"false", "0"}:
        return False
    raise ValueError("previous_step_ok must be boolean")


def _normalize_workflow_steps(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("workflow_steps must be a list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized[:6]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _default_stage(status: str) -> str:
    if status == "done":
        return "complete"
    if status == "blocked":
        return "blocked"
    return "act"
