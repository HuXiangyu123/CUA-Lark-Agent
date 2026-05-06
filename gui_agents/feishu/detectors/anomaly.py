"""Shared semantic anomaly detection for Feishu OCR fallback states."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnomalySpec:
    anomaly_type: str
    flag: str
    recovery_hint: str
    keywords: tuple[str, ...]
    min_keyword_matches: int = 1
    strong_keywords: tuple[str, ...] = ()


ANOMALY_SPECS: tuple[AnomalySpec, ...] = (
    AnomalySpec(
        anomaly_type="permission_denied",
        flag="permission_denied_visible",
        recovery_hint="request_permission",
        keywords=("权限不足", "无权限", "需要权限", "申请权限"),
    ),
    AnomalySpec(
        anomaly_type="wrong_surface",
        flag="wrong_surface",
        recovery_hint="navigate_to_correct_page",
        keywords=("页面不存在", "已删除", "已归档"),
    ),
    AnomalySpec(
        anomaly_type="loading",
        flag="loading_visible",
        recovery_hint="retry_after_load",
        keywords=("加载中", "正在加载", "请稍候"),
    ),
    AnomalySpec(
        anomaly_type="blocking_modal",
        flag="blocking_modal_visible",
        recovery_hint="close_modal_or_wait",
        keywords=("确定", "取消", "知道了", "关闭", "重试"),
        min_keyword_matches=2,
        strong_keywords=("知道了", "重试"),
    ),
)

ANOMALY_FLAGS: tuple[str, ...] = tuple(spec.flag for spec in ANOMALY_SPECS)
ANOMALY_FLAG_TO_TYPE: dict[str, str] = {
    spec.flag: spec.anomaly_type for spec in ANOMALY_SPECS
}


def _matched_keywords(text: str, spec: AnomalySpec) -> list[str]:
    return [keyword for keyword in spec.keywords if keyword in text]


def _matches_spec(text: str, spec: AnomalySpec) -> bool:
    matched = _matched_keywords(text, spec)
    if not matched:
        return False
    if any(keyword in text for keyword in spec.strong_keywords):
        return True
    return len(matched) >= spec.min_keyword_matches


def detect_anomaly_product_state(ocr_text: str | None) -> dict[str, Any]:
    """Return semantic anomaly flags inferred from OCR text.

    The returned fields are advisory state only. They intentionally exclude
    coordinates, bbox data, confidence scores, and screenshot dimensions.
    """

    text = str(ocr_text or "")
    if not text.strip():
        return {}

    product_state: dict[str, Any] = {}
    anomaly_types: list[str] = []
    recovery_hint: str | None = None

    for spec in ANOMALY_SPECS:
        if not _matches_spec(text, spec):
            continue
        product_state[spec.flag] = True
        anomaly_types.append(spec.anomaly_type)
        if recovery_hint is None:
            recovery_hint = spec.recovery_hint

    if anomaly_types:
        product_state["anomaly_types"] = anomaly_types
    if recovery_hint:
        product_state["recovery_hint"] = recovery_hint
    return product_state


def merge_anomaly_product_state(
    product_state: dict[str, Any],
    ocr_text: str | None,
) -> dict[str, Any]:
    """Merge OCR-derived anomaly flags into an existing product state."""

    merged = dict(product_state)
    merged.update(detect_anomaly_product_state(ocr_text))
    return merged
