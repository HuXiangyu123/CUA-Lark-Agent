"""Shared contracts for the Feishu GUI agent domain layer."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

FailureType = Literal[
    "recognition",
    "location",
    "action",
    "verification",
    "timeout",
    "precondition",
    "runtime",
]

ActionId = Literal[
    "open_docs_home",
    "open_docs_new_menu",
    "open_chat",
    "select_blank_doc_template",
    "select_docs_document_type",
    "focus_message_input",
    "type_doc_body",
    "type_doc_title",
    "type_message",
    "send_message",
]

TargetId = Literal[
    "docs_blank_doc_card",
    "docs_body_editor",
    "docs_document_option",
    "docs_new_card",
    "docs_title_input",
    "global_search_entry",
    "conversation_list_item",
    "conversation_search_entry",
    "conversation_search_close_button",
    "conversation_search_result_item",
    "search_result_item",
    "message_input",
    "send_button",
    "vc_home",
    "vc_start_card",
    "vc_join_card",
    "vc_start_button",
    "vc_meeting_id_input",
    "vc_join_button",
    "vc_invite_button",
    "vc_invite_contact_result",
    "vc_share_button",
]

AssertionId = Literal[
    "base_editor_ready",
    "base_home_ready",
    "base_new_menu_opened",
    "base_template_gallery_ready",
    "calendar_event_modal_ready",
    "calendar_home_ready",
    "chat_title_matched",
    "doc_body_contains_text",
    "doc_editor_ready",
    "doc_title_contains_text",
    "docs_home_ready",
    "docs_new_menu_opened",
    "docs_share_dialog_opened",
    "docs_template_gallery_ready",
    "im_search_panel_ready",
    "im_search_results_visible",
    "message_input_contains_text",
    "message_sent",
    "vc_home_ready",
    "vc_invite_dialog_opened",
    "vc_start_preview_ready",
    "vc_meeting_active",
    "vc_join_preview_ready",
    "vc_meeting_id_entered",
    "vc_joined",
]


class TestStep(TypedDict):
    step_id: str
    action: ActionId
    target: str | None
    payload: dict[str, Any] | None
    assertion: str | None


class TestCase(TypedDict):
    id: str
    product: str
    title: str
    preconditions: list[str]
    steps: list[TestStep]
    assertions: list[str]
    artifacts: NotRequired[dict[str, Any]]


class PageDescriptor(TypedDict):
    page_id: str
    page_type: str
    display_name: str
    layout_hints: dict[str, Any]
    key_regions: dict[str, Any]
    text_anchors: list[str]
    supported_workflows: NotRequired[list[str]]
    ui_version_tag: str


class FeishuState(TypedDict):
    page_type: str
    product: str
    chat_name: str | None
    message_input_visible: bool
    send_button_visible: bool
    search_box_visible: bool
    modal_type: str | None
    last_error_banner: str | None
    product_state: dict[str, Any]


class LocatorResult(TypedDict):
    matched: bool
    strategy: str
    page_id: str | None
    target: NotRequired[str | None]
    action_target: NotRequired[dict[str, Any] | None]
    failure_type: NotRequired[FailureType | None]
    failure_reason: NotRequired[str | None]


class ActionLog(TypedDict):
    timestamp: str
    step_id: str
    stage: str
    action: str
    target: str | None
    params: dict[str, Any]
    status: str


class StepResult(TypedDict):
    step_id: str
    stage: str
    action: str
    target: str | None
    status: str
    locator_result: dict[str, Any]
    verification_result: dict[str, Any]
    failure_type: FailureType | None
    failure_reason: str | None


class RuntimeContext(TypedDict):
    run_id: str
    status: str
    intent: str | None
    params: dict[str, Any]
    page_id: str | None
    precondition_results: list[dict[str, Any]]
    action_logs: list[ActionLog]
    screenshots: list[str]
    step_results: list[StepResult]
    failure_type: FailureType | None
    failure_reason: str | None
    started_at: str
    product: NotRequired[str | None]
    task_id: NotRequired[str | None]
    task_title: NotRequired[str | None]
    assertion_plan: NotRequired[list[dict[str, Any]]]
    recovery_attempts: NotRequired[int]
    anomaly_events: NotRequired[list[dict[str, Any]]]
    semantic_steps: NotRequired[list[dict[str, Any]]]
