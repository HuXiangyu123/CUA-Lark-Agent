"""LangChain-based perception and action agents for GUI control."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from agent.json_utils import extract_json_object


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
    sent_message_status_visible: bool = False
    sent_message_status_kind: str = ""
    sent_message_status_evidence: str = ""
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
    """Wrap two structured vision agents for perception and action routing.

    This intentionally calls the OpenAI-compatible client directly instead of
    LangChain's agent wrapper. Some providers support vision reliably through
    the streaming Responses API but return an empty final ``output`` object for
    non-streaming image requests, so the response text is collected from stream
    deltas.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None,
        perception_system_prompt: str,
        action_system_prompt: str,
    ):
        self.model = model
        timeout = float(os.environ.get("GUI_VLM_TIMEOUT_SECONDS", os.environ.get("CUA_VLM_TIMEOUT_SECONDS", "90")))
        self.client = OpenAI(api_key=api_key or "missing-api-key", base_url=base_url, timeout=timeout)
        self.perception_system_prompt = perception_system_prompt
        self.action_system_prompt = action_system_prompt

    def perceive(self, prompt: str, data_url: str) -> tuple[PerceptionRouteStateModel, str]:
        raw = self._complete_json(
            system_prompt=self.perception_system_prompt,
            prompt=_json_prompt(prompt, PerceptionRouteStateModel),
            data_url=data_url,
            temperature=0.0,
        )
        payload = _extract_json_object(raw)
        structured = PerceptionRouteStateModel.model_validate(payload)
        return structured, json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)

    def decide(self, prompt: str, data_url: str) -> tuple[ActionRouteDecisionModel, str]:
        raw = self._complete_json(
            system_prompt=self.action_system_prompt,
            prompt=_json_prompt(prompt, ActionRouteDecisionModel),
            data_url=data_url,
            temperature=0.2,
        )
        payload = _extract_json_object(raw)
        structured = ActionRouteDecisionModel.model_validate(payload)
        return structured, json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)

    def _complete_json(self, *, system_prompt: str, prompt: str, data_url: str, temperature: float) -> str:
        try:
            return self._complete_json_responses_stream(
                system_prompt=system_prompt,
                prompt=prompt,
                data_url=data_url,
                temperature=temperature,
            )
        except Exception as responses_error:
            try:
                return self._complete_json_chat(
                    system_prompt=system_prompt,
                    prompt=prompt,
                    data_url=data_url,
                    temperature=temperature,
                )
            except Exception as chat_error:
                raise RuntimeError(
                    "VLM request failed with both Responses streaming and Chat Completions. "
                    f"Responses error: {responses_error}. Chat error: {chat_error}"
                ) from chat_error

    def _complete_json_responses_stream(self, *, system_prompt: str, prompt: str, data_url: str, temperature: float) -> str:
        stream = self.client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
            text={"format": {"type": "json_object"}},
            max_output_tokens=4096,
            stream=True,
        )
        chunks: list[str] = []
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                chunks.append(getattr(event, "delta", "") or "")
            elif event_type == "response.failed":
                response = getattr(event, "response", None)
                error = getattr(response, "error", None)
                raise RuntimeError(error or "response.failed")
        content = "".join(chunks).strip()
        if not content:
            raise RuntimeError("model returned empty streamed content")
        return content

    def _complete_json_chat(self, *, system_prompt: str, prompt: str, data_url: str, temperature: float) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("model returned empty content")
        return content


def _json_prompt(prompt: str, model_type: type[BaseModel]) -> str:
    schema = model_type.model_json_schema()
    return (
        f"{prompt}\n\n"
        "Return only one valid JSON object. Do not wrap it in Markdown. "
        "The JSON object must match this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    payload = extract_json_object(text)
    if payload is None:
        raise ValueError("model response must be a JSON object")
    return payload
