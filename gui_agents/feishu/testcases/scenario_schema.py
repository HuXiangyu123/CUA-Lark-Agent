"""Schema helpers for structured Feishu test cases."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from gui_agents.feishu.contracts import TestCase, TestStep


DEFAULT_PRECONDITIONS = {
    "base": ["飞书桌面端已登录"],
    "docs": ["飞书桌面端已登录"],
    "im": ["飞书桌面端已登录"],
    "vc": ["飞书桌面端已登录"],
}

VALID_ACTION_IDS = {
    "open_docs_home",
    "open_docs_new_menu",
    "select_docs_document_type",
    "select_blank_doc_template",
    "type_doc_title",
    "type_doc_body",
    "open_chat",
    "focus_message_input",
    "type_message",
    "send_message",
}


def _slug_token(text: str) -> str:
    ascii_text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if ascii_text:
        return ascii_text[:24]
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def make_testcase_id(product: str, title: str) -> str:
    return f"tc_{_slug_token(product)}_{_slug_token(title)}"


def normalize_step(raw_step: dict[str, Any], index: int) -> TestStep:
    action = raw_step.get("action")
    if not action:
        raise ValueError(f"step_{index} missing action")
    if action not in VALID_ACTION_IDS:
        raise ValueError(f"step_{index} invalid action: {action}")

    payload = raw_step.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise ValueError(f"step_{index} payload must be dict or None")

    target = raw_step.get("target")
    if target is not None and not isinstance(target, str):
        raise ValueError(f"step_{index} target must be str or None")

    assertion = raw_step.get("assertion")
    if assertion is not None and not isinstance(assertion, str):
        raise ValueError(f"step_{index} assertion must be str or None")

    return TestStep(
        step_id=raw_step.get("step_id") or f"step_{index}",
        action=action,
        target=target,
        payload=payload,
        assertion=assertion,
    )


def infer_assertions(steps: list[TestStep]) -> list[str]:
    assertions: list[str] = []
    for step in steps:
        assertion = step.get("assertion")
        if assertion:
            assertions.append(assertion)
    if "message_sent" not in assertions and any(
        step["action"] == "send_message" for step in steps
    ):
        assertions.append("message_sent")
    return assertions


def build_testcase(
    *,
    product: str,
    title: str,
    steps: list[dict[str, Any]],
    preconditions: list[str] | None = None,
    assertions: list[str] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> TestCase:
    normalized_steps = [
        normalize_step(step, index) for index, step in enumerate(steps, start=1)
    ]
    testcase = TestCase(
        id=make_testcase_id(product, title),
        product=product,
        title=title,
        preconditions=preconditions or DEFAULT_PRECONDITIONS.get(product, []),
        steps=normalized_steps,
        assertions=assertions or infer_assertions(normalized_steps),
    )
    if artifacts is not None:
        testcase["artifacts"] = artifacts
    validate_testcase(testcase)
    return testcase


def build_guidance_testcase(
    *,
    product: str,
    title: str,
    intent: str,
    params: dict[str, Any] | None = None,
    preconditions: list[str] | None = None,
    assertions: list[str] | None = None,
) -> TestCase:
    testcase = TestCase(
        id=make_testcase_id(product, title),
        product=product,
        title=title,
        preconditions=preconditions or DEFAULT_PRECONDITIONS.get(product, []),
        steps=[],
        assertions=assertions or [],
        artifacts={
            "semantic_guidance_only": True,
            "active_executor": "feishu_agent",
            "intent": intent,
            "params": params or {},
        },
    )
    validate_testcase(testcase)
    return testcase


def validate_testcase(testcase: TestCase) -> None:
    required_fields = ["id", "product", "title", "preconditions", "steps", "assertions"]
    for field in required_fields:
        if field not in testcase:
            raise ValueError(f"testcase missing field: {field}")

    guidance_only = bool(testcase.get("artifacts", {}).get("semantic_guidance_only"))
    if not testcase["steps"] and not guidance_only:
        raise ValueError("testcase must contain at least one step")

    for index, step in enumerate(testcase["steps"], start=1):
        if "step_id" not in step or "action" not in step:
            raise ValueError(f"step_{index} missing required fields")
