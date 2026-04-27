"""LangChain-based perception and action agents for GUI control."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class ActionRouteActionModel(BaseModel):
    type: Literal["click", "double_click", "right_click", "drag", "scroll", "type", "hotkey", "wait"]
    target: str = ""
    x: int | None = None
    y: int | None = None
    end_x: int | None = None
    end_y: int | None = None
    text: str | None = None
    keys: list[str] | None = None
    scroll_amount: int | None = None
    duration_ms: int | None = None


class ActionRouteDecisionModel(BaseModel):
    status: Literal["continue", "done", "blocked"]
    stage: str
    current_state: str
    progress_assessment: str
    previous_step_ok: bool | None = None
    success_criteria: str
    completion_evidence: str = ""
    done_reason: str = ""
    workflow_steps: list[str] = Field(default_factory=list)
    active_step_index: int | None = None
    action: ActionRouteActionModel | None = None


class PerceptionRouteStateModel(BaseModel):
    stage: str = "observe"
    ui_summary: str
    primary_view: str = ""
    selected_sidebar_item: str = ""
    chat_title: str = ""
    composer_visible: bool = False
    composer_focused: bool = False
    composer_text: str = ""
    composer_placeholder: str = ""
    composer_empty: bool = True
    composer_exact_match: bool = False
    send_button_visible: bool = False
    sent_message_visible: bool = False
    sent_message_exact_match: bool = False
    latest_visible_message: str = ""
    calendar_visible: bool = False
    calendar_today_highlighted: bool = False
    calendar_today_label: str = ""
    calendar_event_editor_visible: bool = False
    calendar_event_editor_title_text: str = ""
    calendar_event_time_range: str = ""
    calendar_save_button_visible: bool = False
    calendar_saved_event_visible: bool = False
    calendar_saved_event_title: str = ""
    blocked: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str


class LangChainGuiAgentSuite:
    """Wrap two structured LangChain agents for perception and action routing."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None,
        perception_system_prompt: str,
        action_system_prompt: str,
    ):
        common_kwargs = {
            "model": model,
        }
        if api_key:
            common_kwargs["api_key"] = api_key
        if base_url:
            common_kwargs["base_url"] = base_url
        perception_model = ChatOpenAI(temperature=0.0, **common_kwargs)
        action_model = ChatOpenAI(temperature=0.2, **common_kwargs)
        self.perception_agent = create_agent(
            model=perception_model,
            tools=[],
            system_prompt=perception_system_prompt,
            response_format=PerceptionRouteStateModel,
        )
        self.action_agent = create_agent(
            model=action_model,
            tools=[],
            system_prompt=action_system_prompt,
            response_format=ActionRouteDecisionModel,
        )

    def perceive(self, prompt: str, data_url: str) -> tuple[PerceptionRouteStateModel, str]:
        result = self.perception_agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ]
            }
        )
        structured = result.get("structured_response")
        if not isinstance(structured, PerceptionRouteStateModel):
            raise RuntimeError(f"perception agent did not return structured_response: {result!r}")
        return structured, json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)

    def decide(self, prompt: str, data_url: str) -> tuple[ActionRouteDecisionModel, str]:
        result = self.action_agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ]
            }
        )
        structured = result.get("structured_response")
        if not isinstance(structured, ActionRouteDecisionModel):
            raise RuntimeError(f"action agent did not return structured_response: {result!r}")
        return structured, json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)
