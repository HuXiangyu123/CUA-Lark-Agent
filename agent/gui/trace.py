"""Trace recording for GUI execution."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class TraceRecorder:
    """Persist screenshots, planner output and final summaries."""

    def __init__(self, root_dir: Path, goal: str, model: str):
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.trace_dir = root_dir / self.run_id
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.summary: dict[str, Any] = {
            "run_id": self.run_id,
            "goal": goal,
            "model": model,
            "mode": "gui",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "initial_state": {},
            "run_state": {},
            "steps": [],
            "final_status": "running",
            "final_reason": "",
            "final_state": {},
        }
        self._flush()

    def write_text(self, name: str, content: str) -> Path:
        path = self.trace_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def append_step(self, step_data: dict[str, Any]) -> None:
        self.summary["steps"].append(step_data)
        if "state_after_action" in step_data:
            self.summary["run_state"] = step_data["state_after_action"]
        self._flush()

    def set_initial_state(self, state: dict[str, Any]) -> None:
        self.summary["initial_state"] = state
        self.summary["run_state"] = state
        self._flush()

    def finish(self, final_status: str, final_reason: str, final_state: dict[str, Any] | None = None) -> None:
        self.summary["final_status"] = final_status
        self.summary["final_reason"] = final_reason
        if final_state is not None:
            self.summary["final_state"] = final_state
            self.summary["run_state"] = final_state
        self._flush()
        self._write_markdown()

    def _flush(self) -> None:
        path = self.trace_dir / "summary.json"
        path.write_text(json.dumps(self.summary, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_markdown(self) -> None:
        lines = [
            f"# GUI Trace {self.run_id}",
            "",
            f"- Goal: {self.summary['goal']}",
            f"- Model: {self.summary['model']}",
            f"- Final Status: {self.summary['final_status']}",
            f"- Final Reason: {self.summary['final_reason']}",
            f"- Initial State: {json.dumps(self.summary['initial_state'], ensure_ascii=False)}",
            f"- Final State: {json.dumps(self.summary['final_state'], ensure_ascii=False)}",
            "",
            "## Steps",
            "",
        ]
        for step in self.summary["steps"]:
            lines.append(f"### Step {step['step_index']}")
            lines.append(f"- Observation: {step['observation_path']}")
            lines.append(f"- Planner status: {step['decision']['status']}")
            lines.append(f"- Planner stage: {step['decision'].get('stage', '')}")
            lines.append(f"- Action: {step['action']}")
            lines.append(f"- Result: {step['execution']['detail']}")
            lines.append(f"- Visual State: {json.dumps(step.get('visual_state', {}), ensure_ascii=False)}")
            lines.append(f"- State Before: {json.dumps(step.get('state_before_action', {}), ensure_ascii=False)}")
            lines.append(f"- State After: {json.dumps(step.get('state_after_action', {}), ensure_ascii=False)}")
            lines.append("")
        (self.trace_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
