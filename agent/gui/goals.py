"""Goal classification and target extraction helpers for GUI runs."""

from __future__ import annotations

import re


_QUOTE_PAIRS = (
    ("“", "”"),
    ("‘", "’"),
    ('"', '"'),
    ("'", "'"),
)


def classify_goal_kind(goal: str) -> str:
    goal_text = goal.lower()
    target_message = extract_target_message(goal)

    if looks_like_emoji_goal(goal):
        return "send_emoji"
    if looks_like_calendar_event_creation_goal(goal):
        return "create_calendar_event"
    if looks_like_open_calendar_goal(goal):
        return "open_calendar"
    if looks_like_clear_composer_goal(goal):
        return "clear_composer"
    if looks_like_compose_without_send_goal(goal):
        return "compose_message"

    send_keywords = ("send", "发送", "发出")
    message_keywords = ("message", "消息", "聊天", "chat", "群聊", "群里", "窗口")
    if any(keyword in goal_text for keyword in send_keywords) and (
        any(keyword in goal_text for keyword in message_keywords) or bool(target_message)
    ):
        return "send_message"

    if looks_like_open_chat_goal(goal):
        return "open_chat"

    return "generic"


def extract_target_message(goal: str) -> str:
    quoted = extract_first_quoted_text(goal)
    if quoted:
        return quoted

    compose_patterns = (
        r"(?:输入框输入|输入|填入|写入)\s*[:：]?\s*(.+?)(?:[，,。;；]\s*(?:但)?(?:不要发送|不发送|不发出)|$)",
        r"(?:type|input|enter)\s*[:： ]+(.+?)(?:[,;]\s*(?:but\s+)?(?:do\s+not|don't|without)\s+send|$)",
    )
    for pattern in compose_patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            return _clean_extracted_text(match.group(1))

    fallback_patterns = (
        r"发送(?:消息|对应消息)?\s*[:：]\s*([^\n，,。;；]+)",
        r"send message\s*[:： ]\s*([^\n;,.]+)",
    )
    for pattern in fallback_patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            return _clean_extracted_text(match.group(1))

    return ""


def looks_like_compose_without_send_goal(goal: str) -> bool:
    goal_text = goal.lower()
    no_send_markers = (
        "不要发送",
        "不发送",
        "不要发出",
        "不发出",
        "别发送",
        "do not send",
        "don't send",
        "without sending",
        "not send",
        "unsent",
    )
    compose_markers = (
        "输入",
        "写入",
        "填入",
        "草稿",
        "type",
        "input",
        "enter",
        "draft",
    )
    return any(marker in goal_text for marker in no_send_markers) and any(
        marker in goal_text for marker in compose_markers
    )


def looks_like_clear_composer_goal(goal: str) -> bool:
    goal_text = goal.lower()
    clear_markers = (
        "清空",
        "清除",
        "删除",
        "删掉",
        "移除",
        "clear",
        "delete",
        "remove",
    )
    composer_markers = (
        "输入框",
        "草稿",
        "composer",
        "draft",
        "input box",
        "message box",
    )
    no_send_markers = (
        "不要发送",
        "不发送",
        "不要发出",
        "不发出",
        "do not send",
        "don't send",
        "without sending",
        "no message",
    )
    return any(marker in goal_text for marker in clear_markers) and (
        any(marker in goal_text for marker in composer_markers)
        or any(marker in goal_text for marker in no_send_markers)
    )


def extract_target_label(goal: str, goal_kind: str) -> str:
    if goal_kind in {"open_calendar", "create_calendar_event"}:
        return "Calendar"
    if goal_kind != "open_chat":
        return ""

    quoted = extract_first_quoted_text(goal)
    if quoted:
        return quoted

    patterns = (
        r"(?:打开|进入|切换到|切到|点开|点击|click|open|switch to)[^\"'“”‘’\n]{0,30}(?:群聊|聊天|会话|chat|conversation)\s*[:：]?\s*([^\n，,。;；]+)",
        r"(?:群聊|聊天|会话|chat|conversation)\s*[:：]\s*([^\n，,。;；]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            return _clean_extracted_text(match.group(1))

    return ""


def extract_first_quoted_text(goal: str) -> str:
    for left, right in _QUOTE_PAIRS:
        pattern = f"{re.escape(left)}([^{re.escape(right)}]{{1,200}}){re.escape(right)}"
        match = re.search(pattern, goal)
        if match:
            return match.group(1).strip()
    return ""


def extract_calendar_event_title(goal: str, goal_kind: str) -> str:
    if goal_kind != "create_calendar_event":
        return ""

    labeled_patterns = (
        r"(?:标题为|标题是|event title|title is|title)\s*[:：]?\s*[“\"']?([^”\"'\n，,。;；]{1,120})[”\"']?",
        r"(?:命名为|名称为)\s*[“\"']?([^”\"'\n，,。;；]{1,120})[”\"']?",
    )
    for pattern in labeled_patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            return _clean_extracted_text(match.group(1))

    return extract_first_quoted_text(goal)


def extract_calendar_time_hint(goal: str, goal_kind: str) -> str:
    if goal_kind != "create_calendar_event":
        return ""

    patterns = (
        r"\b\d{1,2}:\d{2}\s?(?:am|pm)?(?:\s*(?:-|to|至|到)\s*\d{1,2}:\d{2}\s?(?:am|pm)?)?",
        r"\b\d{1,2}\s?(?:am|pm)\b",
        r"\d{1,2}\s*点(?:\s*\d{1,2}\s*分?)?(?:\s*(?:-|至|到)\s*\d{1,2}\s*点(?:\s*\d{1,2}\s*分?)?)?",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""


def looks_like_emoji_goal(goal: str) -> bool:
    text = goal.lower()
    return any(keyword in text for keyword in ("emoji", "smiley", "emoticon", "表情", "笑脸"))


def looks_like_calendar_goal(goal: str) -> bool:
    text = goal.lower()
    return any(keyword in text for keyword in ("calendar", "日历", "日程"))


def looks_like_calendar_event_creation_goal(goal: str) -> bool:
    text = goal.lower()
    if not looks_like_calendar_goal(goal):
        return False
    return any(
        keyword in text
        for keyword in (
            "create event",
            "new event",
            "创建event",
            "创建 event",
            "创建日程",
            "新建日程",
            "创建会议",
            "新建会议",
            "time slot",
            "时间节点",
            "时间槽",
        )
    )


def looks_like_open_calendar_goal(goal: str) -> bool:
    text = goal.lower()
    if not looks_like_calendar_goal(goal):
        return False
    return any(keyword in text for keyword in ("open", "打开", "进入", "切换", "切到", "go to"))


def looks_like_open_chat_goal(goal: str) -> bool:
    text = goal.lower()
    chat_keywords = ("chat", "群聊", "聊天", "会话", "conversation")
    open_keywords = ("open", "switch", "click", "打开", "切换", "进入", "点开", "点击")
    return any(keyword in text for keyword in chat_keywords) and any(keyword in text for keyword in open_keywords)


def _clean_extracted_text(text: str) -> str:
    return text.strip().strip("\"'“”‘’").strip()
