"""Rule-based parser for natural-language Feishu test instructions."""

from __future__ import annotations

import re
from typing import Any

from gui_agents.feishu.contracts import TestCase
from gui_agents.feishu.testcases.scenario_schema import (
    build_guidance_testcase,
    build_testcase,
)


SEMANTIC_TESTCASE_ARTIFACTS = {
    "runtime_contract": "semantic_validation_only",
    "active_executor": "feishu_agent",
    "ordered_steps_role": "acceptance_scaffold_not_workflow",
}


QUOTED_TEXT_PATTERN = re.compile(r"""["'“”‘’]([^"'“”‘’]+)["'“”‘’]""")
UNSUPPORTED_INTENT_KEYWORDS = (
    "随机",
    "表情图标",
)


def _extract_quoted_texts(instruction: str) -> list[str]:
    quoted = [match.strip() for match in QUOTED_TEXT_PATTERN.findall(instruction)]
    modern_quoted = [
        match.strip()
        for match in re.findall(r"""["'“”‘’]([^"'“”‘’]+)["'“”‘’]""", instruction)
    ]
    for value in modern_quoted:
        if value and value not in quoted:
            quoted.append(value)
    return quoted


def _detect_product(instruction: str) -> str:
    if any(
        keyword in instruction
        for keyword in (
            "视频会议",
            "会议 ID",
            "会议ID",
            "会议号",
            "会议码",
            "发起会议",
            "加入会议",
        )
    ):
        return "vc"
    if any(
        keyword in instruction for keyword in ("多维表格", "Base", "base", "数据表")
    ):
        return "base"
    if any(keyword in instruction for keyword in ("云文档", "文档", "飞书云文档")):
        return "docs"
    if any(keyword in instruction for keyword in ("日历", "日程")):
        return "calendar"
    return "im"


def _reject_unsupported_intents(instruction: str) -> None:
    matched = [
        keyword
        for keyword in UNSUPPORTED_INTENT_KEYWORDS
        if keyword.lower() in instruction.lower()
    ]
    if matched:
        raise ValueError(
            "current Feishu MVP supports text send_message only; unsupported intents: "
            + ", ".join(matched)
        )


def _extract_chat_name(instruction: str, quoted_texts: list[str]) -> str | None:
    if len(quoted_texts) >= 2:
        return quoted_texts[0]

    for pattern in (
        r"打开(?:消息中的)?(.+?)(?:群聊|会话|聊天|对话)",
        r"(?:在|向|给)(.+?)(?:发送|发|回复|输入)",
    ):
        match = re.search(pattern, instruction)
        if match:
            candidate = match.group(1).strip(" 的里中到给向在消息")
            if candidate:
                return candidate

    # Current milestone supports a single chat target only. Expressions such as
    # "在测试群和产品群发送消息" are not disambiguated yet and will need a richer
    # parser once multi-target workflows are introduced.
    return None


def _extract_message_text(instruction: str, quoted_texts: list[str]) -> str | None:
    if len(quoted_texts) >= 2:
        return quoted_texts[1]

    if len(quoted_texts) == 1 and any(
        keyword in instruction for keyword in ("发送", "发消息", "回复", "输入")
    ):
        return quoted_texts[0]

    for pattern in (
        r"消息发送框输入(.+?)(?:并且|并|然后|再|，|。|$)",
        r"(?:输入|发送|回复|发)(.+?)(?:并且|并|然后|再|，|。|$)",
    ):
        match = re.search(pattern, instruction)
        if match:
            candidate = match.group(1).strip("消息内容为:： ")
            candidate = re.sub(r"^(?:框输入|输入)", "", candidate).strip()
            if candidate:
                return candidate

    return None


def _extract_docs_title(instruction: str, quoted_texts: list[str]) -> str | None:
    if len(quoted_texts) >= 2 and "标题" in instruction:
        return quoted_texts[0]
    if quoted_texts:
        return quoted_texts[0]

    for pattern in (
        r"(?:标题|名为|命名为)\s*[:：]?\s*([^\s，,。；;]+)",
        r"输入标题\s*([^\s，,。；;]+)",
    ):
        match = re.search(pattern, instruction)
        if match:
            return match.group(1).strip()
    return None


def _extract_docs_body_text(instruction: str, quoted_texts: list[str]) -> str | None:
    if len(quoted_texts) >= 3:
        return quoted_texts[2]
    if len(quoted_texts) >= 2 and any(
        keyword in instruction for keyword in ("正文", "内容", "输入内容", "编辑文本")
    ):
        return quoted_texts[-1]

    for pattern in (
        r"""(?:正文|内容|输入内容|编辑文本)\s*[:：]?\s*["'“”‘’]([^"'“”‘’]+)["'“”‘’]""",
        r"(?:正文|内容|输入内容|编辑文本)\s*[:：]?\s*([^\n。；;]+)",
    ):
        match = re.search(pattern, instruction)
        if match:
            candidate = match.group(1).strip(" ，,。；;")
            if candidate:
                return candidate
    return None


def _parse_docs_instruction(instruction: str, quoted_texts: list[str]) -> TestCase:
    if not any(keyword in instruction for keyword in ("创建", "新建")):
        raise ValueError("current Docs MVP supports create_doc_and_edit only")

    doc_title = _extract_docs_title(instruction, quoted_texts)
    if not doc_title:
        raise ValueError("unable to extract doc_title from instruction")
    body_text = _extract_docs_body_text(instruction, quoted_texts)

    steps = [
        {
            "action": "open_docs_home",
            "target": "docs_home",
            "payload": None,
            "assertion": "docs_home_ready",
        },
        {
            "action": "open_docs_new_menu",
            "target": "docs_new_card",
            "payload": None,
            "assertion": "docs_new_menu_opened",
        },
        {
            "action": "select_docs_document_type",
            "target": "docs_document_option",
            "payload": None,
            "assertion": "docs_template_gallery_ready",
        },
        {
            "action": "select_blank_doc_template",
            "target": "docs_blank_doc_card",
            "payload": None,
            "assertion": "doc_editor_ready",
        },
        {
            "action": "type_doc_title",
            "target": "docs_title_input",
            "payload": {"text": doc_title},
            "assertion": "doc_title_contains_text",
        },
    ]
    if body_text:
        steps.append(
            {
                "action": "type_doc_body",
                "target": "docs_body_editor",
                "payload": {"text": body_text},
                "assertion": "doc_body_contains_text",
            }
        )

    return build_testcase(
        product="docs",
        title=f"创建云文档并编辑标题 {doc_title}",
        steps=steps,
        artifacts=dict(SEMANTIC_TESTCASE_ARTIFACTS),
    )


def _parse_base_instruction(instruction: str, quoted_texts: list[str]) -> TestCase:
    title = quoted_texts[0] if quoted_texts else "Base semantic task"
    return build_guidance_testcase(
        product="base",
        title=f"Base 语义指导任务 {title}",
        intent="base_semantic_task",
        params={"instruction": instruction, "title_hint": title},
        assertions=["base_home_ready"],
    )


def _extract_calendar_title(instruction: str, quoted_texts: list[str]) -> str | None:
    if len(quoted_texts) >= 1:
        for pattern in (
            r"""标题[为是]?\s*[:：]?\s*["'“”]([^"'“”]+)["'“”]""",
            r"标题[为是]?\s*[:：]?\s*([^\s，,。；;]+)",
        ):
            match = re.search(pattern, instruction)
            if match:
                return match.group(1).strip().strip("\"'“”")
        return quoted_texts[-1]
    for pattern in (
        r"标题[为是]?\s*[:：]?\s*([^\s，,。；;]+)",
        r"名称为\s*[:：]?\s*([^\s，,。；;]+)",
    ):
        match = re.search(pattern, instruction)
        if match:
            return match.group(1).strip()
    return None


def _extract_calendar_attendee(instruction: str) -> str | None:
    for pattern in (
        r"邀请\s*([^\s，,。；;]+)",
        r"添加参会人\s*([^\s，,。；;]+)",
    ):
        match = re.search(pattern, instruction)
        if match:
            return match.group(1).strip()
    return None


def _parse_calendar_instruction(instruction: str, quoted_texts: list[str]) -> TestCase:
    if any(keyword in instruction for keyword in ("创建", "新建", "添加")):
        intent = "create_event"
        assertions: list[str] = ["calendar_home_ready", "calendar_event_modal_ready"]
    elif any(
        keyword in instruction for keyword in ("查看", "查看今日", "今天", "今日日程")
    ):
        intent = "view_today"
        assertions = ["calendar_home_ready"]
    else:
        intent = "calendar_semantic_task"
        assertions = ["calendar_home_ready"]

    event_title = _extract_calendar_title(instruction, quoted_texts)
    attendee = _extract_calendar_attendee(instruction)

    params: dict[str, Any] = {
        "instruction": instruction,
        "calendar_intent": intent,
    }
    if event_title:
        params["event_title"] = event_title
    if attendee:
        params["attendee"] = attendee

    return build_guidance_testcase(
        product="calendar",
        title=f"Calendar 语义指导任务 {intent}",
        intent=intent,
        params=params,
        assertions=assertions,
    )


def _parse_vc_instruction(instruction: str, quoted_texts: list[str]) -> TestCase:
    del quoted_texts
    if any(
        keyword in instruction
        for keyword in ("加入会议", "会议 ID", "会议ID", "会议号", "会议码")
    ):
        intent = "join_video_meeting"
        assertions = ["vc_join_preview_ready", "vc_joined"]
    elif any(
        keyword in instruction for keyword in ("邀请", "分享邀请", "复制入会信息")
    ):
        intent = "invite_video_meeting"
        assertions = ["vc_meeting_active"]
    else:
        intent = "start_video_meeting"
        assertions = ["vc_start_preview_ready", "vc_meeting_active"]
    return build_guidance_testcase(
        product="vc",
        title=f"VC 语义指导任务 {intent}",
        intent=intent,
        params={"instruction": instruction},
        assertions=assertions,
    )


def parse_instruction(instruction: str) -> TestCase:
    normalized = instruction.strip()
    if not normalized:
        raise ValueError("instruction cannot be empty")

    _reject_unsupported_intents(normalized)
    product = _detect_product(normalized)
    quoted_texts = _extract_quoted_texts(normalized)
    if product == "base":
        return _parse_base_instruction(normalized, quoted_texts)
    if product == "vc":
        return _parse_vc_instruction(normalized, quoted_texts)
    if product == "docs":
        return _parse_docs_instruction(normalized, quoted_texts)
    if product == "calendar":
        return _parse_calendar_instruction(normalized, quoted_texts)

    # IM product: detect search vs send_message intent
    if product == "im" and any(
        kw in normalized for kw in ("搜索", "查找", "搜索消息", "搜索会话")
    ):
        if quoted_texts:
            search_term = quoted_texts[0]
        else:
            search_term = normalized.split("搜索")[-1].strip("“” 消息内容记录")
        chat_name = _extract_chat_name(normalized, quoted_texts)
        params: dict[str, Any] = {"instruction": normalized, "search_term": search_term}
        if chat_name:
            params["chat_name"] = chat_name
        return build_guidance_testcase(
            product="im",
            title=f"IM 搜索任务 {search_term[:20]}",
            intent="search_messages",
            params=params,
            assertions=["im_search_panel_ready"],
        )

    chat_name = _extract_chat_name(normalized, quoted_texts)
    message_text = _extract_message_text(normalized, quoted_texts)
    if not chat_name:
        raise ValueError("unable to extract chat_name from instruction")
    if not message_text:
        raise ValueError("unable to extract message_text from instruction")

    title = f"在{chat_name}发送消息并验证发送成功"

    return build_testcase(
        product=product,
        title=title,
        steps=[
            {
                "action": "open_chat",
                "target": chat_name,
                "payload": None,
                "assertion": "chat_title_matched",
            },
            {
                "action": "type_message",
                "target": "message_input",
                "payload": {"text": message_text},
                "assertion": "message_input_contains_text",
            },
            {
                "action": "send_message",
                "target": "send_button",
                "payload": None,
                "assertion": "message_sent",
            },
        ],
        artifacts=dict(SEMANTIC_TESTCASE_ARTIFACTS),
    )
