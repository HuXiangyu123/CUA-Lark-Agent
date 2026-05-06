import copy
import ctypes
import json
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import pyautogui
from gui_agents.feishu.reports.dashboard_server import (
    DashboardServerHandle,
    start_dashboard_server,
)

try:
    from openai import OpenAI

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CLI_APP = os.path.join(PROJECT_DIR, "gui_agents", "s3", "cli_app.py")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
ENV_FILE = os.path.join(PROJECT_DIR, "env.txt")
HISTORY_FILE = os.path.join(PROJECT_DIR, "command_history.json")
EVAL_SUITE_FILE = os.path.join(
    PROJECT_DIR, "tests", "eval_suite", "feishu_eval_suite.json"
)
ARTIFACT_TEST_RUNS_DIR = os.path.join(PROJECT_DIR, "artifacts", "test_runs")
ARTIFACT_EVALUATION_DIR = os.path.join(PROJECT_DIR, "artifacts", "evaluation")

CANDIDATE_COMMANDS = [
    "打开消息中的 bot 功能测试群聊，发送“Hello World”，并确认消息已发送",
    "在消息中搜索“项目周报”，打开相关会话并停留在搜索结果上下文",
    "新建一个云文档，标题为“项目周报”，正文输入“2026年M2项目进展”",
    "打开云文档首页，找到“项目周报”文档并进入编辑页面",
    "打开云文档中的“项目周报”，点击分享并检查分享弹窗是否出现",
    "打开日历，创建明天下午 2 点的日程，标题为“项目同步”，并邀请张三",
    "打开日历主页，查看今天的日程安排并确认日历页面已打开",
    "新建一个多维表格，标题为“测试用例记录表”",
    "打开多维表格主页，进入最近的表格并确认编辑器可用",
    "发起视频会议并验证进入会议中页面",
    "加入会议 ID 为 123456789 的视频会议并验证进入会议",
    "在当前视频会议中打开邀请面板并确认邀请入口可见",
]

MAIN_PROVIDERS = {
    "volcano": {
        "label": "火山引擎 (Doubao)",
        "provider": "openai",
        "default_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "",
        "model_label": "Endpoint ID",
        "key_label": "API Key",
        "has_reasoning": False,
    },
    "openai_gpt": {
        "label": "OpenAI GPT",
        "provider": "openai",
        "default_url": "https://right.codes/codex/v1",
        "default_model": "gpt-5.4",
        "model_label": "模型名",
        "key_label": "API Key",
        "has_reasoning": True,
    },
}

GROUND_PROVIDERS = {
    "doubao_ark": {
        "label": "火山定位 (Doubao)",
        "provider": "openai",
        "default_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-1-6-vision-250815",
        "coord_range": 1000,
        "image_max_dim": 2000,
    },
    "open_router": {
        "label": "OpenRouter",
        "provider": "open_router",
        "default_url": "https://openrouter.ai/api/v1",
        "default_model": "bytedance/ui-tars-1.5-7b",
        "coord_range": 1920,
        "image_max_dim": 1920,
    },
    "openai": {
        "label": "OpenAI Vision",
        "provider": "openai",
        "default_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "coord_range": 1920,
        "image_max_dim": 1920,
    },
}

GROUND_PROVIDER_ALIASES = {
    "volcano": "doubao_ark",
    "doubao": "doubao_ark",
}

EXECUTION_MODES = {
    "classic_s3": {
        "label": "老 S3 稳定方法",
        "summary": "classic_s3",
    },
    "feishu_agent": {
        "label": "新 Feishu Agent 流程",
        "summary": "feishu_agent",
    },
}


def _warn(message: str) -> None:
    print(f"[launcher warning] {message}", file=sys.stderr)


def _default_config() -> dict:
    return {
        "first_run_completed": False,
        "main_provider": "volcano",
        "main_providers": {
            key: {
                "model_api_key": "",
                "model_id": spec["default_model"],
                "model_url": spec["default_url"],
            }
            for key, spec in MAIN_PROVIDERS.items()
        },
        "ground_provider": "doubao_ark",
        "ground_providers": {
            key: {
                "api_key": "",
                "model": spec["default_model"],
                "url": spec["default_url"],
            }
            for key, spec in GROUND_PROVIDERS.items()
        },
        "reflection_mode": "on_failure",
        "reasoning_effort": "medium",
        "budget": 25,
        "execution_mode": "feishu_agent",
        "grounding_overrides": {},
        "detected_environment": None,
        "model_api_key": "",
        "model_id": "",
        "model_url": MAIN_PROVIDERS["volcano"]["default_url"],
        "ground_api_key": "",
        "ground_model": GROUND_PROVIDERS["doubao_ark"]["default_model"],
        "ground_url": GROUND_PROVIDERS["doubao_ark"]["default_url"],
    }


DEFAULT_CONFIG = _default_config()


def _parse_env_txt(path: str) -> dict:
    result = {}
    if not os.path.exists(path):
        return result
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _normalize_ground_provider(key: str) -> str:
    key = GROUND_PROVIDER_ALIASES.get(key, key)
    return key if key in GROUND_PROVIDERS else DEFAULT_CONFIG["ground_provider"]


def _infer_main_provider(raw: dict) -> str:
    probe = f"{raw.get('model_id', '')} {raw.get('model_url', '')}".lower()
    if "gpt" in probe or "openai" in probe or "right.codes" in probe:
        return "openai_gpt"
    return "volcano"


def _sync_flat_fields(cfg: dict):
    main_key = cfg["main_provider"]
    ground_key = cfg["ground_provider"]
    main_cfg = cfg["main_providers"][main_key]
    ground_cfg = cfg["ground_providers"][ground_key]
    cfg["model_api_key"] = main_cfg["model_api_key"]
    cfg["model_id"] = main_cfg["model_id"]
    cfg["model_url"] = main_cfg["model_url"]
    cfg["ground_api_key"] = ground_cfg["api_key"]
    cfg["ground_model"] = ground_cfg["model"]
    cfg["ground_url"] = ground_cfg["url"]


def _apply_env_defaults(cfg: dict, had_main_routing: bool):
    env = _parse_env_txt(ENV_FILE)
    main_ark_key = (
        env.get("VOLCANO_API_KEY")
        or env.get("ARK_MAIN_API_KEY")
        or env.get("api-key", "")
        or env.get("ARK_API_KEY", "")
    )
    main_endpoint_id = (
        env.get("VOLCANO_ENDPOINT_ID")
        or env.get("ARK_MAIN_ENDPOINT_ID")
        or env.get("ep-id", "")
    )
    ground_ark_key = env.get("ARK_API_KEY") or env.get("GROUND_API_KEY") or main_ark_key

    volcano_cfg = cfg["main_providers"]["volcano"]
    current_volcano_key = volcano_cfg.get("model_api_key", "")
    should_repair_legacy_fallback = (
        current_volcano_key
        and env.get("api-key")
        and env.get("ARK_API_KEY")
        and current_volcano_key == env.get("ARK_API_KEY")
        and env.get("api-key") != env.get("ARK_API_KEY")
    )
    if main_ark_key and (not current_volcano_key or should_repair_legacy_fallback):
        volcano_cfg["model_api_key"] = main_ark_key
    if main_endpoint_id and not volcano_cfg["model_id"]:
        volcano_cfg["model_id"] = main_endpoint_id

    gpt_cfg = cfg["main_providers"]["openai_gpt"]
    if env.get("oai_api") and not gpt_cfg["model_api_key"]:
        gpt_cfg["model_api_key"] = env["oai_api"]
    if env.get("oai_base_url") and (
        not gpt_cfg["model_url"]
        or gpt_cfg["model_url"] == MAIN_PROVIDERS["openai_gpt"]["default_url"]
    ):
        gpt_cfg["model_url"] = env["oai_base_url"]
    if env.get("model") and (
        not gpt_cfg["model_id"]
        or gpt_cfg["model_id"] == MAIN_PROVIDERS["openai_gpt"]["default_model"]
    ):
        gpt_cfg["model_id"] = env["model"]

    doubao_ground = cfg["ground_providers"]["doubao_ark"]
    if ground_ark_key and not doubao_ground["api_key"]:
        doubao_ground["api_key"] = ground_ark_key

    if (
        env.get("model_reasoning_effort")
        and cfg["reasoning_effort"] == DEFAULT_CONFIG["reasoning_effort"]
    ):
        cfg["reasoning_effort"] = env["model_reasoning_effort"]
    if (
        env.get("reflection_mode")
        and cfg["reflection_mode"] == DEFAULT_CONFIG["reflection_mode"]
    ):
        cfg["reflection_mode"] = env["reflection_mode"]

    _sync_flat_fields(cfg)


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    raw = {}
    had_main_routing = False
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception as exc:
            _warn(f"load_config failed, using defaults: {exc!r}")
            raw = {}
    had_main_routing = "main_provider" in raw or "main_providers" in raw

    cfg.update(raw)
    if cfg.get("execution_mode") not in EXECUTION_MODES:
        cfg["execution_mode"] = DEFAULT_CONFIG["execution_mode"]
    cfg["main_provider"] = cfg.get("main_provider") or _infer_main_provider(raw)
    cfg["ground_provider"] = _normalize_ground_provider(
        cfg.get("ground_provider", "doubao_ark")
    )

    merged_main = copy.deepcopy(DEFAULT_CONFIG["main_providers"])
    merged_ground = copy.deepcopy(DEFAULT_CONFIG["ground_providers"])

    if "main_providers" in raw:
        for key, values in raw["main_providers"].items():
            if key in merged_main:
                merged_main[key].update(values)
    else:
        inferred = _infer_main_provider(raw)
        merged_main[inferred].update(
            {
                "model_api_key": raw.get("model_api_key", ""),
                "model_id": raw.get("model_id", ""),
                "model_url": raw.get("model_url", merged_main[inferred]["model_url"]),
            }
        )

    if "ground_providers" in raw:
        for key, values in raw["ground_providers"].items():
            key = _normalize_ground_provider(key)
            if key in merged_ground:
                merged_ground[key].update(values)
    else:
        active_ground = cfg["ground_provider"]
        merged_ground[active_ground].update(
            {
                "api_key": raw.get("ground_api_key", ""),
                "model": raw.get("ground_model", merged_ground[active_ground]["model"]),
                "url": raw.get("ground_url", merged_ground[active_ground]["url"]),
            }
        )

    cfg["main_providers"] = merged_main
    cfg["ground_providers"] = merged_ground

    _apply_env_defaults(cfg, had_main_routing)
    return cfg


def save_config(cfg: dict):
    _sync_flat_fields(cfg)
    with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, ensure_ascii=False, indent=2)


def detect_environment() -> dict:
    width, height = pyautogui.size()
    dpi_scale = 1.0
    try:
        if platform.system() == "Windows" and hasattr(
            ctypes.windll.user32, "GetDpiForSystem"
        ):
            dpi_scale = round(ctypes.windll.user32.GetDpiForSystem() / 96.0, 2)
    except Exception as exc:
        _warn(f"detect_environment dpi probe failed: {exc!r}")
        dpi_scale = 1.0

    env = {
        "platform": platform.system(),
        "screen_width": width,
        "screen_height": height,
        "dpi_scale": dpi_scale,
        "grounding_recommendations": {},
    }
    for key, spec in GROUND_PROVIDERS.items():
        image_max = spec.get("image_max_dim", spec["coord_range"])
        scale = min(image_max / width, image_max / height, 1.0)
        env["grounding_recommendations"][key] = {
            "width": int(width * scale),
            "height": int(height * scale),
        }
    return env


def _read_json_object(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def mark_run_aborted(
    run_dir: str | Path,
    *,
    run_id: str | None = None,
    reason: str = "launcher manual stop",
) -> dict:
    """Mark an already-created run directory as manually aborted."""

    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    summary_path = path / "summary.json"
    summary = _read_json_object(summary_path) if summary_path.exists() else {}
    resolved_run_id = run_id or summary.get("run_id") or path.name
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary.update(
        {
            "run_id": resolved_run_id,
            "status": "aborted",
            "result": "aborted",
            "failure_type": "manual_stop",
            "failure_reason": reason,
            "completed_at": completed_at,
        }
    )
    manifest = summary.get("artifact_manifest")
    if not isinstance(manifest, dict):
        manifest = {}
    manifest.update(
        {
            "run_dir": str(path),
            "summary": str(summary_path),
            "report": str(path / "report.md"),
            "actions": str(path / "actions.jsonl"),
            "replay_draft": str(path / "replay_draft.md"),
            "runtime_state": str(path / "runtime_state.json"),
            "runtime_stdout": str(path / "runtime_stdout.log"),
            "artifact_error": str(path / "artifact_error.txt"),
        }
    )
    summary["artifact_manifest"] = manifest
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    abort_note = (
        f"\n\n## Manual Stop\n\n"
        f"- Status: `aborted`\n"
        f"- Reason: `{reason}`\n"
        f"- Completed At: `{completed_at}`\n"
    )
    report_path = path / "report.md"
    if report_path.exists():
        report_path.write_text(
            report_path.read_text(encoding="utf-8", errors="replace") + abort_note,
            encoding="utf-8",
        )
    else:
        report_path.write_text(
            f"# Feishu Run Report\n\n- Run ID: `{resolved_run_id}`" + abort_note,
            encoding="utf-8",
        )

    replay_path = path / "replay_draft.md"
    if replay_path.exists():
        replay_path.write_text(
            replay_path.read_text(encoding="utf-8", errors="replace") + abort_note,
            encoding="utf-8",
        )
    else:
        replay_path.write_text(
            f"# Replay Draft - Run {resolved_run_id}\n" + abort_note,
            encoding="utf-8",
        )

    (path / "artifact_error.txt").write_text(
        f"{completed_at} {reason}\n",
        encoding="utf-8",
    )
    return summary


_REPLAY_STEP_FIELDS = {
    "step_index",
    "step_id",
    "product",
    "page_type",
    "visible_controls",
    "action_summary",
    "verification",
    "verification_passed",
    "failure_type",
    "recovery_attempt",
    "timestamp",
}

_FORBIDDEN_REPLAY_TOKENS = (
    "relative_bounds",
    "bbox",
    "bounding_box",
    "coordinate",
    "coordinates",
    "confidence",
    "pixel",
    "pixels",
    "resolution",
    "image_width",
    "image_height",
)

_LEGACY_REPLAY_ARTIFACTS = (
    "summary.json",
    "report.md",
    "actions.jsonl",
    "screenshots",
    "semantic_trace.json",
    "replay_draft.md",
)


def _safe_replay_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    lowered = text.lower()
    if not text or any(token in lowered for token in _FORBIDDEN_REPLAY_TOKENS):
        return None
    if re.search(r"\(\s*\d+\s*,\s*\d+", text):
        return None
    return text


def load_semantic_trace_steps(path: str | os.PathLike | None) -> list[dict]:
    if not path:
        return []
    trace_path = Path(path)
    if not trace_path.exists():
        return []
    try:
        data = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    steps: list[dict] = []
    for raw_step in data:
        if not isinstance(raw_step, dict):
            continue
        step: dict = {}
        for key in _REPLAY_STEP_FIELDS:
            if key not in raw_step:
                continue
            value = raw_step.get(key)
            if key == "visible_controls":
                if not isinstance(value, list):
                    continue
                controls = [
                    item
                    for item in (_safe_replay_text(control) for control in value)
                    if item
                ]
                if controls:
                    step[key] = controls
            elif key in {"verification_passed", "recovery_attempt"}:
                if value is not None:
                    step[key] = bool(value)
            elif key == "step_index":
                if isinstance(value, int):
                    step[key] = value
            else:
                text = _safe_replay_text(value)
                if text is not None:
                    step[key] = text
        if step:
            steps.append(step)
    return steps


def format_replay_step_label(step: dict, ordinal: int) -> str:
    status = "passed" if step.get("verification_passed") else "review"
    if step.get("verification_passed") is False or step.get("failure_type"):
        status = "failed"
    page = step.get("page_type") or "unknown"
    action = step.get("action_summary") or "semantic action"
    return f"{ordinal:02d} | {status} | {page} | {action}"


def render_replay_step_detail(step: dict, ordinal: int) -> str:
    lines = [
        f"Step {ordinal}",
        "",
        f"Step ID: {step.get('step_id') or '<unknown>'}",
        f"Product: {step.get('product') or '<unknown>'}",
        f"Page: {step.get('page_type') or '<unknown>'}",
        f"Action: {step.get('action_summary') or '<not recorded>'}",
    ]
    controls = step.get("visible_controls") or []
    if controls:
        lines.append(f"Visible controls: {', '.join(controls)}")
    if step.get("verification"):
        result = step.get("verification_passed")
        if result is True:
            result_text = "passed"
        elif result is False:
            result_text = "failed"
        else:
            result_text = "not recorded"
        lines.append(f"Verification: {step.get('verification')} ({result_text})")
    if step.get("failure_type"):
        lines.append(f"Failure type: {step.get('failure_type')}")
    if step.get("recovery_attempt"):
        lines.append("Recovery: yes")
    if step.get("timestamp"):
        lines.append(f"Timestamp: {step.get('timestamp')}")
    return "\n".join(lines) + "\n"


def build_replay_review_summary(run: dict, steps: list[dict]) -> dict:
    failed = [
        step
        for step in steps
        if step.get("verification_passed") is False or step.get("failure_type")
    ]
    passed = [step for step in steps if step.get("verification_passed") is True]
    recovered = [step for step in steps if step.get("recovery_attempt")]
    pages = []
    for step in steps:
        page = step.get("page_type")
        if page and page not in pages:
            pages.append(page)

    warnings: list[str] = []
    if not run.get("semantic_trace"):
        warnings.append("missing semantic_trace.json")
    if not run.get("replay_draft"):
        if run.get("report"):
            warnings.append("missing replay_draft.md; showing legacy report.md")
        else:
            warnings.append("missing replay_draft.md")
    if not steps:
        warnings.append("no semantic steps")
    if run.get("screenshots_count", 0) == 0:
        warnings.append("no screenshots")
    for ordinal, step in enumerate(steps, start=1):
        missing = [
            label
            for label, field in (
                ("page", "page_type"),
                ("action", "action_summary"),
                ("verification", "verification"),
            )
            if not step.get(field)
        ]
        if missing:
            warnings.append(f"step {ordinal} missing {', '.join(missing)}")

    return {
        "run_id": run.get("run_id"),
        "product": run.get("product"),
        "status": run.get("status"),
        "steps": len(steps),
        "passed_steps": len(passed),
        "failed_steps": len(failed),
        "recovery_steps": len(recovered),
        "screenshots": run.get("screenshots_count", 0),
        "pages": pages,
        "warnings": warnings,
    }


def render_replay_review_summary(run: dict, steps: list[dict]) -> str:
    summary = build_replay_review_summary(run, steps)
    warnings = summary["warnings"]
    lines = [
        "Replay Review Summary",
        "",
        f"Run: {summary.get('run_id') or '<unknown>'}",
        f"Product: {summary.get('product') or '<unknown>'}",
        f"Status: {summary.get('status') or '<unknown>'}",
        (
            f"Steps: {summary['steps']} total, {summary['passed_steps']} passed, "
            f"{summary['failed_steps']} failed, {summary['recovery_steps']} recovery"
        ),
        f"Screenshots: {summary['screenshots']}",
        f"Page path: {' -> '.join(summary['pages']) if summary['pages'] else '<none>'}",
        f"Warnings: {', '.join(warnings) if warnings else 'none'}",
    ]
    return "\n".join(lines) + "\n"


def discover_semantic_replay_runs(
    artifact_root: str | os.PathLike | None = None,
) -> list[dict]:
    """Discover read-only run artifacts without executing anything."""

    root = Path(artifact_root or ARTIFACT_TEST_RUNS_DIR)
    if not root.exists() or not root.is_dir():
        return []

    runs: list[dict] = []
    for run_dir in root.iterdir():
        if not run_dir.is_dir():
            continue
        replay_path = run_dir / "replay_draft.md"
        trace_path = run_dir / "semantic_trace.json"
        summary_path = run_dir / "summary.json"
        report_path = run_dir / "report.md"
        actions_path = run_dir / "actions.jsonl"
        screenshots_dir = run_dir / "screenshots"
        recognized_paths = [
            run_dir / artifact_name for artifact_name in _LEGACY_REPLAY_ARTIFACTS
        ]
        existing_paths = [path for path in recognized_paths if path.exists()]
        if not existing_paths:
            continue

        summary = _read_json_object(summary_path) if summary_path.exists() else {}
        updated_at = max(path.stat().st_mtime for path in existing_paths)
        trace_steps = load_semantic_trace_steps(trace_path)
        screenshots_count = (
            len([path for path in screenshots_dir.iterdir() if path.is_file()])
            if screenshots_dir.exists()
            else 0
        )
        runs.append(
            {
                "run_id": summary.get("run_id") or run_dir.name,
                "task_id": summary.get("task_id"),
                "task_title": summary.get("task_title")
                or summary.get("task_id")
                or summary.get("intent"),
                "product": summary.get("product"),
                "status": summary.get("status"),
                "run_dir": str(run_dir),
                "summary": str(summary_path) if summary_path.exists() else None,
                "semantic_trace": str(trace_path) if trace_path.exists() else None,
                "replay_draft": str(replay_path) if replay_path.exists() else None,
                "report": str(report_path) if report_path.exists() else None,
                "actions": str(actions_path) if actions_path.exists() else None,
                "trace_steps": len(trace_steps),
                "screenshots_dir": (
                    str(screenshots_dir) if screenshots_dir.exists() else None
                ),
                "screenshots_count": screenshots_count,
                "updated_at": updated_at,
            }
        )
    return sorted(runs, key=lambda item: item["updated_at"], reverse=True)


def select_replay_preview_path(run: dict | None) -> str | None:
    if not run:
        return None
    return run.get("replay_draft") or run.get("report")


def load_replay_draft_preview(
    path: str | os.PathLike | None, limit: int = 20000
) -> str:
    if not path:
        return "该运行没有 replay_draft.md。"
    replay_path = Path(path)
    if not replay_path.exists():
        return "该运行没有 replay_draft.md。"
    text = replay_path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[preview truncated]\n"


def load_replay_artifact_preview(run: dict | None, limit: int = 20000) -> str:
    if not run:
        return "请选择一个运行记录。"
    if run.get("replay_draft"):
        return load_replay_draft_preview(run.get("replay_draft"), limit=limit)
    report_path = run.get("report")
    if not report_path:
        return "该运行没有 replay_draft.md 或 report.md。"
    report = Path(report_path)
    if not report.exists():
        return "该运行没有 replay_draft.md 或 report.md。"
    text = report.read_text(encoding="utf-8", errors="replace")
    prefix = "该运行没有 replay_draft.md，以下显示旧版 report.md。\n\n"
    if len(text) <= limit:
        return prefix + text
    return prefix + text[:limit] + "\n\n[preview truncated]\n"


def open_path_in_shell(path: str | os.PathLike | None) -> bool:
    if not path:
        return False
    target = Path(path)
    if not target.exists():
        return False
    if platform.system() == "Windows":
        os.startfile(str(target))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(
            ["open" if platform.system() == "Darwin" else "xdg-open", str(target)]
        )
    return True


def ensure_dashboard_server(
    handle: DashboardServerHandle | None,
    *,
    artifact_root: str | os.PathLike = ARTIFACT_TEST_RUNS_DIR,
    evaluation_dir: str | os.PathLike = ARTIFACT_EVALUATION_DIR,
) -> DashboardServerHandle:
    if handle is not None and handle.thread.is_alive():
        return handle
    return start_dashboard_server(
        artifact_root=artifact_root,
        evaluation_dir=evaluation_dir,
    )


class Launcher:
    def __init__(self):
        self.colors = {
            "bg": "#f9fafb",
            "panel": "#ffffff",
            "panel_alt": "#f3f4f6",
            "border": "#e5e7eb",
            "text": "#171717",
            "muted": "#737373",
            "accent": "#2563eb",
            "accent_alt": "#0d9488",
            "warn": "#d97706",
            "danger": "#dc2626",
            "success": "#16a34a",
            "button_text": "#ffffff",
            "input_bg": "#f9fafb",
            "input_text": "#171717",
            "log_bg": "#ffffff",
            "dark_panel": "#171717",
            "dark_muted": "#a3a3a3",
        }

        self.root = tk.Tk()
        self.root.title("Agent S3 Launcher")
        self.root.configure(bg=self.colors["bg"])
        self.root.option_add("*TCombobox*Listbox.background", self.colors["panel"])
        self.root.option_add("*TCombobox*Listbox.foreground", self.colors["text"])
        self.root.option_add(
            "*TCombobox*Listbox.selectBackground", self.colors["accent"]
        )
        self.root.option_add(
            "*TCombobox*Listbox.selectForeground", self.colors["button_text"]
        )

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = min(int(screen_w * 0.95), 1400)
        win_h = min(int(screen_h * 0.92), 900)
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(900, 640)

        self.root.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")

        self._in_code_block = False
        self._code_line_count = 0
        self.process = None
        self.output_queue = queue.Queue()
        self.agent_ready = False
        self.dashboard_server_handle: DashboardServerHandle | None = None
        self.cfg = load_config()
        self.command_history = self._load_command_history()
        self._full_command_history = list(self.command_history)
        self.main_paned: tk.PanedWindow | None = None
        self.left_pane: ttk.Frame | None = None
        self.right_pane: ttk.Frame | None = None
        self._main_sash_initialized = False

        if not self.cfg.get("first_run_completed"):
            self.cfg["detected_environment"] = detect_environment()
            self.cfg["first_run_completed"] = True
            save_config(self.cfg)

        self._active_main_key = self.cfg["main_provider"]
        self._active_ground_key = self.cfg["ground_provider"]

        self._configure_styles()
        self._build_state()
        self._build_ui()
        self._apply_main_config(self._active_main_key)
        self._apply_ground_config(self._active_ground_key)
        self._load_resolution_from_config()
        self._refresh_summary()
        self._set_status("未启动", "idle", "等待启动")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            ".", background=self.colors["bg"], foreground=self.colors["text"]
        )
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("Alt.TFrame", background=self.colors["panel_alt"])
        style.configure(
            "Card.TLabelframe",
            background=self.colors["panel"],
            bordercolor=self.colors["border"],
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "App.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "AppMuted.TLabel",
            background=self.colors["bg"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Section.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["accent"],
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Primary.TButton",
            background=self.colors["accent"],
            foreground=self.colors["button_text"],
            padding=(12, 8),
            borderwidth=0,
        )
        style.configure(
            "Subtle.TButton",
            background=self.colors["panel_alt"],
            foreground=self.colors["text"],
            padding=(10, 7),
            borderwidth=1,
        )
        style.configure(
            "Danger.TButton",
            background=self.colors["danger"],
            foreground=self.colors["button_text"],
            padding=(10, 7),
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#1d4ed8"), ("disabled", "#9ca3af")],
            foreground=[("disabled", "#ffffff")],
        )
        style.map(
            "Subtle.TButton",
            background=[("active", "#e5e7eb"), ("disabled", self.colors["panel_alt"])],
            foreground=[("disabled", "#9a9aa1")],
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#b91c1c"), ("disabled", "#fca5a5")],
            foreground=[("disabled", "#ffffff")],
        )
        style.configure("TNotebook", background=self.colors["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            padding=(16, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["panel_alt"]), ("active", "#e8edf9")],
            foreground=[
                ("selected", self.colors["text"]),
                ("active", self.colors["text"]),
            ],
        )
        style.configure(
            "TEntry",
            fieldbackground=self.colors["input_bg"],
            foreground=self.colors["input_text"],
            insertcolor=self.colors["input_text"],
            padding=5,
        )
        style.configure(
            "TCombobox",
            fieldbackground=self.colors["input_bg"],
            foreground=self.colors["input_text"],
            arrowsize=15,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.colors["input_bg"])],
            foreground=[("readonly", self.colors["input_text"])],
            selectbackground=[("readonly", self.colors["input_bg"])],
            selectforeground=[("readonly", self.colors["input_text"])],
        )

    def _build_state(self):
        self.v_status = tk.StringVar()
        self.v_status_detail = tk.StringVar()
        self.v_query = tk.StringVar()
        self.current_run_id = None
        self.current_run_dir = None
        self.v_execution_mode = tk.StringVar(
            value=EXECUTION_MODES[
                self.cfg.get("execution_mode", DEFAULT_CONFIG["execution_mode"])
            ]["label"]
        )
        self.v_main_provider = tk.StringVar()
        self.v_model_key = tk.StringVar()
        self.v_model_id = tk.StringVar()
        self.v_model_url = tk.StringVar()
        self.v_main_key_label = tk.StringVar()
        self.v_main_model_label = tk.StringVar()
        self.v_ground_provider = tk.StringVar()
        self.v_ground_key = tk.StringVar()
        self.v_ground_model = tk.StringVar()
        self.v_ground_url = tk.StringVar()
        self.v_ground_key_label = tk.StringVar()
        self.v_reflection_mode = tk.StringVar(value=self.cfg["reflection_mode"])
        self.v_reasoning_effort = tk.StringVar(value=self.cfg["reasoning_effort"])
        self.v_budget = tk.StringVar(value=str(self.cfg.get("budget", 25)))
        self.v_gw = tk.StringVar()
        self.v_gh = tk.StringVar()
        self.v_screen_info = tk.StringVar()
        self.v_env_info = tk.StringVar()
        self.v_summary_main = tk.StringVar()
        self.v_summary_ground = tk.StringVar()
        self.v_summary_runtime = tk.StringVar()
        self.v_replay_meta = tk.StringVar(value="尚未选择运行")

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, style="App.TFrame", padding=24)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        hero = tk.Frame(
            outer,
            bg=self.colors["panel"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=24,
            pady=16,
        )
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 24))
        hero.columnconfigure(0, weight=1)
        tk.Label(
            hero,
            text="Agent S3 启动器",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Variable Display", 22, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            hero,
            text="路由分发、运行监控与 Feishu Agent 调试面板",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Segoe UI Variable Text", 11),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        hero_actions = tk.Frame(hero, bg=self.colors["panel"])
        hero_actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.status_badge = tk.Label(
            hero_actions,
            textvariable=self.v_status,
            bg=self.colors["panel_alt"],
            fg="#4b5563",
            font=("Segoe UI Variable Text Semibold", 11),
            padx=16,
            pady=8,
        )
        self.status_badge.pack(side="left", padx=(0, 16))
        self.btn_dashboard = ttk.Button(
            hero_actions,
            text="Dashboard",
            style="Subtle.TButton",
            command=self._open_dashboard,
        )
        self.btn_dashboard.pack(side="left", padx=(0, 12))
        self.btn_stop = ttk.Button(
            hero_actions,
            text="停止任务",
            style="Danger.TButton",
            command=self._stop_agent,
            state="disabled",
        )
        self.btn_stop.pack(side="left", padx=(0, 12))
        self.btn_start = ttk.Button(
            hero_actions,
            text="启动智能体",
            style="Primary.TButton",
            command=self._start_agent,
        )
        self.btn_start.pack(side="left")

        self.main_paned = tk.PanedWindow(
            outer,
            orient=tk.HORIZONTAL,
            bg=self.colors["bg"],
            bd=0,
            relief="flat",
            sashwidth=10,
            sashrelief="flat",
            showhandle=False,
            opaqueresize=True,
        )
        self.main_paned.grid(row=1, column=0, sticky="nsew")
        self.main_paned.bind("<Configure>", self._maybe_initialize_main_split, add="+")

        left_pane = ttk.Frame(self.main_paned, style="App.TFrame")
        left_pane.columnconfigure(0, weight=1)
        left_pane.rowconfigure(1, weight=1)
        self.left_pane = left_pane

        switcher = tk.Frame(left_pane, bg=self.colors["border"], padx=4, pady=4)
        switcher.grid(row=0, column=0, sticky="w", pady=(0, 16))
        tab_agent = tk.Label(
            switcher,
            text="智能体工作台",
            bg=self.colors["panel"],
            fg=self.colors["accent"],
            font=("Segoe UI Variable Display", 11, "bold"),
            padx=24,
            pady=8,
            cursor="hand2",
        )
        tab_agent.grid(row=0, column=0)
        tab_sop = tk.Label(
            switcher,
            text="SOP 快捷面板",
            bg=self.colors["border"],
            fg=self.colors["muted"],
            font=("Segoe UI Variable Display", 11),
            padx=24,
            pady=8,
            cursor="hand2",
        )
        tab_sop.grid(row=0, column=1)
        tab_replay = tk.Label(
            switcher,
            text="语义回放",
            bg=self.colors["border"],
            fg=self.colors["muted"],
            font=("Segoe UI Variable Display", 11),
            padx=24,
            pady=8,
            cursor="hand2",
        )
        tab_replay.grid(row=0, column=2)

        tab_stack = ttk.Frame(left_pane, style="App.TFrame")
        tab_stack.grid(row=1, column=0, sticky="nsew")
        tab_stack.columnconfigure(0, weight=1)
        tab_stack.rowconfigure(0, weight=1)
        agent_tab = tk.Frame(
            tab_stack,
            bg=self.colors["panel"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        sop_tab = tk.Frame(
            tab_stack,
            bg=self.colors["panel"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        replay_tab = tk.Frame(
            tab_stack,
            bg=self.colors["panel"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        agent_tab.grid(row=0, column=0, sticky="nsew")
        sop_tab.grid(row=0, column=0, sticky="nsew")
        replay_tab.grid(row=0, column=0, sticky="nsew")

        self._build_agent_tab(agent_tab)
        self._build_sop_tab(sop_tab)
        self._build_replay_tab(replay_tab)
        agent_tab.tkraise()

        def activate_tab(active_label, active_frame):
            for label in (tab_agent, tab_sop, tab_replay):
                label.configure(
                    bg=self.colors["border"],
                    fg=self.colors["muted"],
                    font=("Segoe UI Variable Display", 11),
                )
            active_label.configure(
                bg=self.colors["panel"],
                fg=self.colors["accent"],
                font=("Segoe UI Variable Display", 11, "bold"),
            )
            active_frame.tkraise()

        def switch_to_agent(_event=None):
            activate_tab(tab_agent, agent_tab)

        def switch_to_sop(_event=None):
            activate_tab(tab_sop, sop_tab)

        def switch_to_replay(_event=None):
            activate_tab(tab_replay, replay_tab)
            self._reload_replay_runs()

        tab_agent.bind("<Button-1>", switch_to_agent)
        tab_sop.bind("<Button-1>", switch_to_sop)
        tab_replay.bind("<Button-1>", switch_to_replay)

        right_pane = ttk.Frame(self.main_paned, style="App.TFrame")
        right_pane.columnconfigure(0, weight=1)
        right_pane.rowconfigure(2, weight=1)
        self.right_pane = right_pane
        self._build_right_pane(right_pane)
        self.main_paned.add(left_pane, minsize=360)
        self.main_paned.add(right_pane, minsize=480)
        self.root.after_idle(self._maybe_initialize_main_split)

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(1, weight=1)
        ttk.Label(
            footer, textvariable=self.v_status_detail, style="AppMuted.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            footer, text="Agent S3 / Feishu desktop runtime", style="AppMuted.TLabel"
        ).grid(row=0, column=1, sticky="e")

    def _build_agent_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        canvas = tk.Canvas(parent, bg=self.colors["panel"], highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)

        inner = ttk.Frame(canvas, style="Panel.TFrame", padding=24)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(inner_id, width=e.width))
        self._agent_canvas = canvas
        self._agent_inner = inner

        inner.columnconfigure(0, weight=1)

        cfg = ttk.LabelFrame(
            inner, text="运行配置", style="Card.TLabelframe", padding=14
        )
        cfg.grid(row=0, column=0, sticky="nsew")
        cfg.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(cfg, text="主模型", style="Section.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        row += 1
        ttk.Label(cfg, text="Provider", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        self.cb_main = ttk.Combobox(
            cfg,
            textvariable=self.v_main_provider,
            values=[v["label"] for v in MAIN_PROVIDERS.values()],
            state="readonly",
            width=24,
        )
        self.cb_main.grid(row=row, column=1, sticky="w", pady=3)
        self.cb_main.bind("<<ComboboxSelected>>", self._on_main_changed)
        row += 1
        ttk.Label(cfg, textvariable=self.v_main_key_label, style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(cfg, textvariable=self.v_model_key, show="*").grid(
            row=row, column=1, sticky="ew", pady=3
        )
        row += 1
        ttk.Label(cfg, textvariable=self.v_main_model_label, style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(cfg, textvariable=self.v_model_id).grid(
            row=row, column=1, sticky="ew", pady=3
        )
        row += 1
        ttk.Label(cfg, text="主模型 URL", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(cfg, textvariable=self.v_model_url).grid(
            row=row, column=1, sticky="ew", pady=3
        )
        row += 1
        ttk.Separator(cfg, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=12
        )
        row += 1
        ttk.Label(cfg, text="定位模型", style="Section.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        row += 1
        ttk.Label(cfg, text="Provider", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        self.cb_ground = ttk.Combobox(
            cfg,
            textvariable=self.v_ground_provider,
            values=[v["label"] for v in GROUND_PROVIDERS.values()],
            state="readonly",
            width=24,
        )
        self.cb_ground.grid(row=row, column=1, sticky="w", pady=3)
        self.cb_ground.bind("<<ComboboxSelected>>", self._on_ground_changed)
        row += 1
        ttk.Label(cfg, textvariable=self.v_ground_key_label, style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(cfg, textvariable=self.v_ground_key, show="*").grid(
            row=row, column=1, sticky="ew", pady=3
        )
        row += 1
        ttk.Label(cfg, text="定位模型名", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(cfg, textvariable=self.v_ground_model).grid(
            row=row, column=1, sticky="ew", pady=3
        )
        row += 1
        ttk.Label(cfg, text="定位 URL", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(cfg, textvariable=self.v_ground_url).grid(
            row=row, column=1, sticky="ew", pady=3
        )
        row += 1
        ttk.Label(cfg, text="定位分辨率", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        res_row = ttk.Frame(cfg, style="App.TFrame")
        res_row.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Entry(res_row, textvariable=self.v_gw, width=8).pack(side="left")
        ttk.Label(res_row, text=" × ", style="App.TLabel").pack(side="left")
        ttk.Entry(res_row, textvariable=self.v_gh, width=8).pack(side="left")
        ttk.Label(res_row, textvariable=self.v_screen_info, style="Muted.TLabel").pack(
            side="left", padx=(10, 0)
        )
        row += 1
        ttk.Separator(cfg, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=12
        )
        row += 1
        ttk.Label(cfg, text="运行策略", style="Section.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        row += 1
        ttk.Label(cfg, text="Reflection", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        self.cb_reflection = ttk.Combobox(
            cfg,
            textvariable=self.v_reflection_mode,
            values=("full", "reduced", "on_failure", "off"),
            state="readonly",
            width=18,
        )
        self.cb_reflection.grid(row=row, column=1, sticky="w", pady=3)
        row += 1
        ttk.Label(cfg, text="Reasoning", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        self.cb_reasoning = ttk.Combobox(
            cfg,
            textvariable=self.v_reasoning_effort,
            values=("low", "medium", "high", "xhigh"),
            state="readonly",
            width=18,
        )
        self.cb_reasoning.grid(row=row, column=1, sticky="w", pady=3)
        row += 1
        ttk.Label(cfg, text="执行模式", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        self.cb_execution_mode = ttk.Combobox(
            cfg,
            textvariable=self.v_execution_mode,
            values=[spec["label"] for spec in EXECUTION_MODES.values()],
            state="readonly",
            width=18,
        )
        self.cb_execution_mode.grid(row=row, column=1, sticky="w", pady=3)
        self.cb_execution_mode.bind(
            "<<ComboboxSelected>>", self._on_execution_mode_changed
        )
        row += 1
        ttk.Label(cfg, text="Step Budget", style="App.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(cfg, textvariable=self.v_budget, width=12).grid(
            row=row, column=1, sticky="w", pady=3
        )
        row += 1
        actions = ttk.Frame(cfg, style="App.TFrame")
        actions.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(
            actions, text="保存配置", style="Subtle.TButton", command=self._save_config
        ).pack(side="left")
        ttk.Button(
            actions,
            text="恢复 Doubao 1.6 Vision",
            style="Subtle.TButton",
            command=self._restore_doubao_legacy,
        ).pack(side="left", padx=(8, 0))

    def _build_right_pane(self, parent):
        panel = tk.Frame(parent, bg=self.colors["dark_panel"], padx=24, pady=24)
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)

        main_box = tk.Frame(panel, bg=self.colors["dark_panel"])
        main_box.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        tk.Label(
            main_box,
            text="COMPUTE",
            bg=self.colors["dark_panel"],
            fg=self.colors["dark_muted"],
            font=("Segoe UI Variable Text", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            main_box,
            textvariable=self.v_summary_main,
            bg=self.colors["dark_panel"],
            fg="#ffffff",
            font=("Segoe UI Variable Display", 10, "bold"),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        canvas_box = tk.Frame(panel, bg=self.colors["dark_panel"])
        canvas_box.grid(row=0, column=1, sticky="nsew")
        tk.Label(
            canvas_box,
            text="CANVAS",
            bg=self.colors["dark_panel"],
            fg=self.colors["dark_muted"],
            font=("Segoe UI Variable Text", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            canvas_box,
            textvariable=self.v_screen_info,
            bg=self.colors["dark_panel"],
            fg="#ffffff",
            font=("Segoe UI Variable Display", 10, "bold"),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        controls = ttk.Frame(parent, style="App.TFrame")
        controls.grid(row=1, column=0, sticky="w", pady=(0, 16))
        ttk.Button(
            controls,
            text="测试连接",
            style="Subtle.TButton",
            command=self._test_connectivity,
        ).pack(side="left")
        ttk.Button(
            controls,
            text="重新检测",
            style="Subtle.TButton",
            command=self._redetect_environment,
        ).pack(side="left", padx=(10, 0))
        ttk.Button(
            controls,
            text="清空日志",
            style="Subtle.TButton",
            command=self._clear_logs,
        ).pack(side="left", padx=(10, 0))

        log_frame = tk.Frame(
            parent,
            bg=self.colors["panel"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        log_header = tk.Frame(
            log_frame,
            bg=self.colors["input_bg"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=24,
            pady=12,
        )
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(1, weight=1)
        tk.Label(
            log_header,
            text="实时任务流水",
            bg=self.colors["input_bg"],
            fg=self.colors["muted"],
            font=("Segoe UI Variable Display", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            log_header,
            textvariable=self.v_summary_runtime,
            bg=self.colors["input_bg"],
            fg=self.colors["muted"],
            font=("Segoe UI Variable Text", 9),
        ).grid(row=0, column=1, sticky="e")

        self.log = scrolledtext.ScrolledText(
            log_frame,
            wrap="word",
            height=16,
            font=("Cascadia Code", 10),
            state="disabled",
            bg=self.colors["log_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            bd=0,
            padx=24,
            pady=24,
        )
        self.log.grid(row=1, column=0, sticky="nsew")
        self.log.bind(
            "<MouseWheel>",
            lambda e: self.log.yview_scroll(-1 * (e.delta // 120), "units"),
        )
        self.log.tag_config("info", foreground=self.colors["accent"])
        self.log.tag_config("action", foreground=self.colors["accent_alt"])
        self.log.tag_config("warn", foreground=self.colors["warn"])
        self.log.tag_config("query", foreground="#6b7280")
        self.log.tag_config("success", foreground=self.colors["success"])
        self.log.tag_config("muted", foreground=self.colors["muted"])
        self.log.tag_config("normal", foreground=self.colors["text"])

        inp = tk.Frame(
            log_frame,
            bg=self.colors["panel"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=24,
            pady=16,
        )
        inp.grid(row=2, column=0, sticky="ew")
        inp.columnconfigure(0, weight=1)
        self.cb_query = ttk.Combobox(
            inp,
            textvariable=self.v_query,
            values=self.command_history,
            font=("Microsoft YaHei UI", 11),
            state="disabled",
        )
        self.cb_query.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.cb_query.bind("<Return>", lambda _event: self._send_query())
        self.cb_query.bind("<KeyRelease>", self._on_query_keyrelease)
        self.cb_query.bind("<FocusOut>", lambda _e: self._hide_suggestions())
        self._suggestion_popup: tk.Toplevel | None = None
        self._suggestion_listbox: tk.Listbox | None = None
        self.btn_pull = ttk.Button(
            inp,
            text="拉取示例",
            style="Subtle.TButton",
            command=self._show_example_dialog,
        )
        self.btn_pull.grid(row=0, column=1, padx=(0, 10))
        self.btn_pull.configure(state="disabled")
        self.btn_send = ttk.Button(
            inp,
            text="发送指令",
            style="Primary.TButton",
            command=self._send_query,
            state="disabled",
        )
        self.btn_send.grid(row=0, column=2)

    def _maybe_initialize_main_split(self, _event=None):
        if self._main_sash_initialized or self.main_paned is None:
            return
        if len(self.main_paned.panes()) < 2:
            return

        total_width = self.main_paned.winfo_width()
        if total_width <= 1:
            self.root.after(50, self._maybe_initialize_main_split)
            return

        desired_left = int(total_width * 0.42)
        min_left = 360
        min_right = 520
        sash_x = max(min_left, min(desired_left, total_width - min_right))
        if sash_x <= 0:
            return

        try:
            sash_y = self.main_paned.sash_coord(0)[1]
            self.main_paned.sash_place(0, sash_x, sash_y)
        except tk.TclError:
            self.root.after(50, self._maybe_initialize_main_split)
            return
        self._main_sash_initialized = True

    def _build_sop_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        bar = ttk.Frame(parent, style="Panel.TFrame", padding=(24, 16))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            bar, text="刷新 SOP 列表", style="Subtle.TButton", command=self._reload_sops
        ).pack(side="left")
        ttk.Label(
            bar, text="点击卡片并填写参数后即可执行预设工作流。", style="Muted.TLabel"
        ).pack(side="left", padx=(12, 0))
        canvas = tk.Canvas(parent, bg=self.colors["panel"], highlightthickness=0, bd=0)
        canvas.grid(row=1, column=0, sticky="nsew", padx=24)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)
        self._sop_canvas = canvas
        self._sop_frame = ttk.Frame(canvas, style="Panel.TFrame")
        self._sop_frame_id = canvas.create_window(
            (0, 0), window=self._sop_frame, anchor="nw"
        )
        self._sop_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfig(self._sop_frame_id, width=event.width),
        )
        log = ttk.LabelFrame(
            parent, text="SOP 日志", style="Card.TLabelframe", padding=10
        )
        log.grid(row=2, column=0, columnspan=2, sticky="ew", padx=24, pady=(16, 24))
        log.columnconfigure(0, weight=1)
        self.sop_log = scrolledtext.ScrolledText(
            log,
            wrap="word",
            height=6,
            font=("Cascadia Code", 9),
            state="disabled",
            bg=self.colors["log_bg"],
            fg=self.colors["text"],
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
        )
        self.sop_log.grid(row=0, column=0, sticky="ew")
        self.sop_log.bind(
            "<MouseWheel>",
            lambda e: self.sop_log.yview_scroll(-1 * (e.delta // 120), "units"),
        )
        self.sop_log.tag_config("ok", foreground="#30a050")
        self.sop_log.tag_config("err", foreground="#ff3b30")
        self.sop_log.tag_config("info", foreground="#4a6cf7")
        self._reload_sops()

    def _build_replay_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        bar = ttk.Frame(parent, style="Panel.TFrame", padding=(24, 16))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            bar,
            text="刷新回放列表",
            style="Subtle.TButton",
            command=self._reload_replay_runs,
        ).pack(side="left")
        ttk.Button(
            bar,
            text="打开运行目录",
            style="Subtle.TButton",
            command=self._open_selected_replay_dir,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            bar,
            text="打开草稿/报告",
            style="Primary.TButton",
            command=self._open_selected_replay_draft,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            bar,
            text="打开截图目录",
            style="Subtle.TButton",
            command=self._open_selected_screenshots_dir,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            bar,
            text="复制审阅摘要",
            style="Subtle.TButton",
            command=self._copy_replay_review_summary,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            bar,
            text="只读查看 semantic_trace.json / replay_draft.md，不执行回放。",
            style="Muted.TLabel",
        ).pack(side="left", padx=(12, 0))

        content = ttk.Frame(parent, style="Panel.TFrame", padding=(24, 0, 24, 16))
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=2)
        content.columnconfigure(1, weight=3)
        content.rowconfigure(0, weight=1)

        list_frame = ttk.LabelFrame(
            content, text="运行记录", style="Card.TLabelframe", padding=10
        )
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.replay_listbox = tk.Listbox(
            list_frame,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.colors["button_text"],
            font=("Microsoft YaHei UI", 9),
            activestyle="none",
            exportselection=False,
            borderwidth=0,
            highlightthickness=0,
        )
        self.replay_listbox.grid(row=0, column=0, sticky="nsew")
        replay_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.replay_listbox.yview
        )
        replay_scroll.grid(row=0, column=1, sticky="ns")
        self.replay_listbox.configure(yscrollcommand=replay_scroll.set)
        self.replay_listbox.bind("<<ListboxSelect>>", self._on_replay_select)
        self.replay_listbox.bind(
            "<Double-Button-1>", lambda _event: self._open_selected_replay_draft()
        )

        preview_frame = ttk.LabelFrame(
            content, text="回放草稿预览", style="Card.TLabelframe", padding=10
        )
        preview_frame.grid(row=0, column=1, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(2, weight=1)
        preview_frame.rowconfigure(4, weight=2)
        ttk.Label(
            preview_frame,
            textvariable=self.v_replay_meta,
            style="Muted.TLabel",
            wraplength=520,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.replay_overview = scrolledtext.ScrolledText(
            preview_frame,
            wrap="word",
            height=7,
            font=("Cascadia Code", 9),
            state="disabled",
            bg=self.colors["input_bg"],
            fg=self.colors["text"],
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
        )
        self.replay_overview.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        timeline = ttk.Frame(preview_frame, style="Panel.TFrame")
        timeline.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        timeline.columnconfigure(0, weight=2)
        timeline.columnconfigure(1, weight=3)
        timeline.rowconfigure(0, weight=1)
        self.replay_step_listbox = tk.Listbox(
            timeline,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.colors["button_text"],
            font=("Microsoft YaHei UI", 9),
            activestyle="none",
            exportselection=False,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        self.replay_step_listbox.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.replay_step_listbox.bind("<<ListboxSelect>>", self._on_replay_step_select)
        self.replay_step_detail = scrolledtext.ScrolledText(
            timeline,
            wrap="word",
            height=8,
            font=("Cascadia Code", 9),
            state="disabled",
            bg=self.colors["log_bg"],
            fg=self.colors["text"],
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
        )
        self.replay_step_detail.grid(row=0, column=1, sticky="nsew")

        ttk.Label(
            preview_frame,
            text="Markdown 回放草稿",
            style="Section.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(0, 6))
        self.replay_preview = scrolledtext.ScrolledText(
            preview_frame,
            wrap="word",
            height=10,
            font=("Cascadia Code", 9),
            state="disabled",
            bg=self.colors["log_bg"],
            fg=self.colors["text"],
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
        )
        self.replay_preview.grid(row=4, column=0, sticky="nsew")
        self._replay_runs: list[dict] = []
        self._selected_replay_index: int | None = None
        self._current_replay_steps: list[dict] = []
        self._reload_replay_runs()

    def _provider_key_from_label(self, table: dict, label: str, default: str) -> str:
        for key, spec in table.items():
            if spec["label"] == label:
                return key
        return default

    def _apply_main_config(self, key: str):
        spec = MAIN_PROVIDERS[key]
        data = self.cfg["main_providers"][key]
        self.v_main_provider.set(spec["label"])
        self.v_main_key_label.set(spec["key_label"])
        self.v_main_model_label.set(spec["model_label"])
        self.v_model_key.set(data["model_api_key"])
        self.v_model_id.set(data["model_id"])
        self.v_model_url.set(data["model_url"] or spec["default_url"])
        self.cb_reasoning.configure(
            state="readonly" if spec["has_reasoning"] else "disabled"
        )

    def _apply_ground_config(self, key: str):
        spec = GROUND_PROVIDERS[key]
        data = self.cfg["ground_providers"][key]
        self.v_ground_provider.set(spec["label"])
        self.v_ground_key_label.set(f"{spec['label']} API Key")
        self.v_ground_key.set(data["api_key"])
        self.v_ground_model.set(data["model"] or spec["default_model"])
        self.v_ground_url.set(data["url"] or spec["default_url"])

    def _persist_current_forms(self):
        self.cfg["main_providers"][self._active_main_key].update(
            {
                "model_api_key": self.v_model_key.get().strip(),
                "model_id": self.v_model_id.get().strip(),
                "model_url": self.v_model_url.get().strip()
                or MAIN_PROVIDERS[self._active_main_key]["default_url"],
            }
        )
        self.cfg["ground_providers"][self._active_ground_key].update(
            {
                "api_key": self.v_ground_key.get().strip(),
                "model": self.v_ground_model.get().strip(),
                "url": self.v_ground_url.get().strip()
                or GROUND_PROVIDERS[self._active_ground_key]["default_url"],
            }
        )
        self.cfg["main_provider"] = self._active_main_key
        self.cfg["ground_provider"] = self._active_ground_key
        self.cfg["reflection_mode"] = self.v_reflection_mode.get().strip()
        self.cfg["reasoning_effort"] = self.v_reasoning_effort.get().strip()
        self.cfg["execution_mode"] = self._execution_mode_key_from_label(
            self.v_execution_mode.get()
        )
        try:
            self.cfg["budget"] = max(1, int(self.v_budget.get().strip()))
        except ValueError:
            self.cfg["budget"] = DEFAULT_CONFIG["budget"]
        _sync_flat_fields(self.cfg)

    def _execution_mode_key_from_label(self, label: str) -> str:
        for key, spec in EXECUTION_MODES.items():
            if spec["label"] == label:
                return key
        return DEFAULT_CONFIG["execution_mode"]

    def _on_main_changed(self, _event=None):
        self._persist_current_forms()
        self._active_main_key = self._provider_key_from_label(
            MAIN_PROVIDERS, self.v_main_provider.get(), "volcano"
        )
        self._apply_main_config(self._active_main_key)
        self._refresh_summary()

    def _on_ground_changed(self, _event=None):
        self._persist_current_forms()
        self._active_ground_key = self._provider_key_from_label(
            GROUND_PROVIDERS, self.v_ground_provider.get(), "doubao_ark"
        )
        self._apply_ground_config(self._active_ground_key)
        self._load_resolution_from_config()
        self._refresh_summary()

    def _on_execution_mode_changed(self, _event=None):
        self._persist_current_forms()
        self._refresh_summary()

    def _load_resolution_from_config(self):
        key = self._active_ground_key
        spec = GROUND_PROVIDERS[key]
        env = self.cfg.get("detected_environment") or detect_environment()
        self.cfg["detected_environment"] = env
        rec = self.cfg.get("grounding_overrides", {}).get(key) or env.get(
            "grounding_recommendations", {}
        ).get(key)
        if rec:
            self.v_gw.set(str(rec["width"]))
            self.v_gh.set(str(rec["height"]))
        else:
            width, height = pyautogui.size()
            scale = min(
                spec["image_max_dim"] / width, spec["image_max_dim"] / height, 1.0
            )
            self.v_gw.set(str(int(width * scale)))
            self.v_gh.set(str(int(height * scale)))
        sw, sh = pyautogui.size()
        self.v_screen_info.set(f"屏幕 {sw}×{sh} · 坐标 0-{spec['coord_range']}")
        self.v_env_info.set(
            f"{env.get('platform', '?')} | {env.get('screen_width', '?')}×{env.get('screen_height', '?')} | 缩放 {int(env.get('dpi_scale', 1.0) * 100)}%"
        )

    def _refresh_summary(self):
        main_spec = MAIN_PROVIDERS[self._active_main_key]
        ground_spec = GROUND_PROVIDERS[self._active_ground_key]
        self.v_summary_main.set(
            f"{main_spec['label']} · {self.v_model_id.get().strip() or main_spec['default_model'] or '<empty>'}"
        )
        self.v_summary_ground.set(
            f"{ground_spec['label']} · {self.v_ground_model.get().strip() or ground_spec['default_model']}"
        )
        mode_key = self._execution_mode_key_from_label(self.v_execution_mode.get())
        mode_summary = EXECUTION_MODES.get(
            mode_key,
            EXECUTION_MODES[DEFAULT_CONFIG["execution_mode"]],
        )["summary"]
        self.v_summary_runtime.set(
            f"mode={mode_summary} · reflection={self.v_reflection_mode.get()} · reasoning={self.v_reasoning_effort.get()} · budget={self.v_budget.get() or 25}"
        )

    def _restore_doubao_legacy(self):
        self._persist_current_forms()
        self._active_ground_key = "doubao_ark"
        self.cfg["ground_provider"] = "doubao_ark"
        self.cfg["ground_providers"]["doubao_ark"]["model"] = GROUND_PROVIDERS[
            "doubao_ark"
        ]["default_model"]
        self._apply_ground_config("doubao_ark")
        self._load_resolution_from_config()
        self._refresh_summary()
        self._set_status(
            "兼容档已恢复", "saved", "已切回 doubao-seed-1-6-vision-250815"
        )

    def _redetect_environment(self):
        self.cfg["detected_environment"] = detect_environment()
        self._load_resolution_from_config()
        self._set_status("环境已刷新", "saved", "已更新屏幕分辨率与推荐配置")

    def _open_dashboard(self):
        try:
            self.dashboard_server_handle = ensure_dashboard_server(
                self.dashboard_server_handle,
                artifact_root=ARTIFACT_TEST_RUNS_DIR,
                evaluation_dir=ARTIFACT_EVALUATION_DIR,
            )
            webbrowser.open_new_tab(self.dashboard_server_handle.url)
            self._set_status(
                "Dashboard ready",
                "saved",
                f"Local evaluation dashboard: {self.dashboard_server_handle.url}",
            )
        except Exception as exc:
            messagebox.showerror("Dashboard error", str(exc))
            self._set_status(
                "Dashboard error",
                "stopped",
                f"Failed to open evaluation dashboard: {exc}",
            )

    def _stop_dashboard_server(self):
        if self.dashboard_server_handle is None:
            return
        try:
            self.dashboard_server_handle.stop()
        except Exception as exc:
            _warn(f"stop dashboard server failed: {exc!r}")
        finally:
            self.dashboard_server_handle = None

    def _test_connectivity(self):
        if not _OPENAI_AVAILABLE:
            self._log("⚠ 测试连通性需要安装 openai 包: pip install openai\n", "warn")
            return

        self._log("\n─── 连通性测试 ───\n", "action")

        main_spec = MAIN_PROVIDERS[self._active_main_key]
        main_model = self.v_model_id.get().strip() or main_spec["default_model"]
        main_url = self.v_model_url.get().strip() or main_spec["default_url"]
        main_key = self.v_model_key.get().strip() or self.cfg["main_providers"].get(
            self._active_main_key, {}
        ).get("model_api_key", "")

        ground_spec = GROUND_PROVIDERS[self._active_ground_key]
        ground_model = self.v_ground_model.get().strip() or ground_spec["default_model"]
        ground_url = self.v_ground_url.get().strip() or ground_spec["default_url"]
        ground_key = (
            self.v_ground_key.get().strip()
            or self.cfg["ground_providers"]
            .get(self._active_ground_key, {})
            .get("api_key", "")
            or main_key
        )
        if not ground_key:
            ground_key = self.cfg["ground_providers"]["doubao_ark"]["api_key"]

        def _test_one(label, base_url, api_key, model):
            if not base_url:
                self._log(f"  ✗ {label}: URL 未配置\n", "warn")
                return
            if not model:
                self._log(f"  ✗ {label}: 模型名未填写\n", "warn")
                return
            if not api_key:
                self._log(f"  ✗ {label}: API Key 未配置\n", "warn")
                return
            t0 = time.time()
            try:
                client = OpenAI(
                    base_url=base_url.rstrip("/"), api_key=api_key, timeout=15.0
                )
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                )
                elapsed = time.time() - t0
                self._log(f"  ✓ {label}: {model} — {elapsed:.2f}s\n", "success")
            except Exception as exc:
                elapsed = time.time() - t0
                msg = str(exc).replace("\n", " ")[:120]
                self._log(f"  ✗ {label}: {model} — {msg} ({elapsed:.1f}s)\n", "warn")

        self._log(f"  主模型:  {main_url}\n", "normal")
        _test_one("主模型", main_url, main_key, main_model)
        self._log(f"  定位模型: {ground_url}\n", "normal")
        _test_one("定位模型", ground_url, ground_key, ground_model)
        self._log("─── 测试完毕 ───\n", "action")

    def _set_status(self, status: str, mode: str, detail: str):
        palette = {
            "idle": "#f3f4f6",
            "starting": "#dbeafe",
            "running": "#dcfce7",
            "ready": "#bbf7d0",
            "saved": "#fef3c7",
            "stopped": "#fee2e2",
        }
        self.status_badge.configure(bg=palette.get(mode, "#f3f4f6"), fg="#374151")
        self.v_status.set(status)
        self.v_status_detail.set(detail)

    def _validate_budget(self) -> int | None:
        try:
            return max(1, int(self.v_budget.get().strip()))
        except ValueError:
            messagebox.showwarning("预算无效", "Step Budget 必须是正整数。")
            return None

    def _start_agent(self):
        if self.process and self.process.poll() is None:
            return
        budget = self._validate_budget()
        if budget is None:
            return
        self._persist_current_forms()
        self._refresh_summary()
        self.agent_ready = False
        self._log("正在启动 Agent S...\n", "info")
        self._set_status("启动中", "starting", "正在拉起 cli_app.py")

        main_spec = MAIN_PROVIDERS[self._active_main_key]
        ground_spec = GROUND_PROVIDERS[self._active_ground_key]
        main_model = self.v_model_id.get().strip() or main_spec["default_model"]
        main_url = self.v_model_url.get().strip() or main_spec["default_url"]
        ground_model = self.v_ground_model.get().strip() or ground_spec["default_model"]
        ground_url = self.v_ground_url.get().strip() or ground_spec["default_url"]
        ground_key = (
            self.v_ground_key.get().strip()
            or self.cfg["ground_providers"]["doubao_ark"]["api_key"]
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = PROJECT_DIR
        env["PYTHONIOENCODING"] = "utf-8"

        cmd = [
            sys.executable,
            CLI_APP,
            "--execution_mode",
            self._execution_mode_key_from_label(self.v_execution_mode.get()),
            "--provider",
            main_spec["provider"],
            "--model",
            main_model,
            "--model_url",
            main_url,
            "--model_api_key",
            self.v_model_key.get().strip(),
            "--ground_provider",
            ground_spec["provider"],
            "--ground_url",
            ground_url,
            "--ground_api_key",
            ground_key,
            "--ground_model",
            ground_model,
            "--grounding_width",
            self.v_gw.get().strip(),
            "--grounding_height",
            self.v_gh.get().strip(),
            "--budget",
            str(budget),
            "--reflection_mode",
            self.v_reflection_mode.get().strip(),
            "--reasoning_effort",
            self.v_reasoning_effort.get().strip(),
        ]
        if ground_spec["coord_range"] != ground_spec["image_max_dim"]:
            cmd.extend(["--ground_coord_scale", str(ground_spec["coord_range"])])

        self.process = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_send.configure(state="disabled")
        self.cb_query.configure(state="disabled")
        self.btn_pull.configure(state="disabled")
        self.log.focus_set()
        self.log.see("end")
        threading.Thread(target=self._read_output, daemon=True).start()
        self._startup_timeout_id = self.root.after(30000, self._check_startup_timeout)
        self.root.after(100, self._poll_output)

    def _stop_agent(self):
        if self.process:
            if self.current_run_dir:
                try:
                    mark_run_aborted(
                        self.current_run_dir,
                        run_id=self.current_run_id,
                        reason="launcher stop button pressed",
                    )
                    self._log(
                        f"\n已标记运行中止：{self.current_run_dir}\n",
                        "warn",
                    )
                except Exception as exc:
                    _warn(f"mark run aborted failed: {exc!r}")
            try:
                self.process.terminate()
            except Exception as exc:
                _warn(f"terminate agent process failed: {exc!r}")
        self._set_stopped()

    def _set_stopped(self):
        if hasattr(self, "_startup_timeout_id") and self._startup_timeout_id:
            self.root.after_cancel(self._startup_timeout_id)
            self._startup_timeout_id = None
        self._in_code_block = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_send.configure(state="disabled")
        self.cb_query.configure(state="disabled")
        self.btn_pull.configure(state="disabled")
        self.agent_ready = False
        self._set_status("已停止", "stopped", "子进程已结束或被终止")
        self._log("\n─── Agent 已停止 ───\n", "warn")

    def _read_output(self):
        buf = ""
        try:
            while True:
                ch = self.process.stdout.read(1)
                if not ch:
                    if buf:
                        self.output_queue.put(buf)
                    self.output_queue.put(None)
                    break
                buf += ch
                if ch == "\n" or buf.endswith("Query: ") or buf.endswith("(y/n): "):
                    self.output_queue.put(buf)
                    buf = ""
        except Exception as exc:
            _warn(f"agent output reader stopped unexpectedly: {exc!r}")
            if buf:
                self.output_queue.put(buf)
            self.output_queue.put(None)

    def _poll_output(self):
        try:
            while True:
                line = self.output_queue.get_nowait()
                if line is None:
                    self._set_stopped()
                    return
                self._handle_line(line)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_output)

    def _check_startup_timeout(self):
        self._startup_timeout_id = None
        if not self.agent_ready and self.process and self.process.poll() is None:
            self._log(
                "⚠️ Agent 启动超时（30秒未就绪），请检查配置或停止并重试\n", "warn"
            )
            self._set_status("超时", "stopped", "启动超时，未收到 Query 信号")

    def _handle_line(self, line: str):
        line = ANSI_ESCAPE.sub("", line)
        line_strip = line.strip()

        if line_strip.startswith("Query:"):
            if not self.agent_ready:
                self.agent_ready = True
                if hasattr(self, "_startup_timeout_id") and self._startup_timeout_id:
                    self.root.after_cancel(self._startup_timeout_id)
                    self._startup_timeout_id = None
                self.btn_send.configure(state="normal")
                self.cb_query.configure(state="normal")
                self.cb_query["values"] = list(self._full_command_history)
                self.btn_pull.configure(state="normal")
                self.cb_query.focus()
                self._set_status("就绪", "ready", "Agent 已完成初始化，可发送任务")
                self._log("✅ Agent 就绪，请在下方输入任务\n", "success")
            return

        if line_strip.startswith("FEISHU_RUNTIME_STARTED:"):
            payload = line_strip.split("FEISHU_RUNTIME_STARTED:", 1)[1].strip()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {}
            self.current_run_id = data.get("run_id") or self.current_run_id
            self.current_run_dir = data.get("run_dir") or self.current_run_dir
            if self.current_run_dir:
                self._log(f"运行产物目录：{self.current_run_dir}\n", "muted")
            return

        if line_strip.startswith("FEISHU_RUNTIME_ARTIFACTS:"):
            self.current_run_id = None
            self.current_run_dir = None
            self._log("结构化运行产物已写入。\n", "success")
            return

        if "Would you like to provide another query" in line:
            self._write_stdin("y\n")
            return

        # Step header — prominent separator
        if "🔄 Step" in line or re.search(r"Step \d+/\d+", line):
            self._in_code_block = False
            self._log("\n─── " + line_strip + " ───\n", "action")
            return

        # Collapse massive exec code blocks to 1-line summary
        if "EXECUTING CODE:" in line:
            self._in_code_block = True
            self._code_line_count = 0
            code_text = line.split("EXECUTING CODE:", 1)[1].strip()
            total_lines = code_text.count("\n") + 1
            first_line = code_text.split("\n")[0].strip()
            # Detect action type for the summary
            hint = first_line
            for keyword in (
                "feishu_click",
                "feishu_type",
                "feishu_doc_click",
                "feishu_doc_type",
                "feishu_focus",
                "pyautogui.click",
                "pyautogui.type",
                "pyautogui.hotkey",
                "pyautogui.press",
            ):
                if keyword in code_text:
                    hint = (
                        code_text[: code_text.index(keyword)]
                        .rsplit("\n", 1)[-1]
                        .strip()
                    )
                    if len(hint) > 100:
                        hint = hint[:97] + "..."
                    break
            if total_lines > 5:
                self._log("▶ " + hint + f"  [{total_lines} 行]\n", "action")
            else:
                self._log("▶ " + code_text + "\n", "action")
            return

        # Inside code block — only show result / settle lines, skip boilerplate
        if getattr(self, "_in_code_block", False):
            self._code_line_count += 1
            if "等待 UI 稳定" in line:
                self._in_code_block = False
                self._log("  " + line_strip + "\n", "normal")
                return
            for prefix, tag in (
                ("FEISHU_UIA_CLICKED:", "success"),
                ("EXEC_CODE_ERROR:", "warn"),
            ):
                if line_strip.startswith(prefix):
                    self._in_code_block = False
                    self._log(
                        "  ✓ " + line_strip.split(prefix, 1)[1].strip() + "\n", tag
                    )
                    return
            for prefix, tag in (
                ("FEISHU_UIA_CLICK_MISS:", "warn"),
                ("FEISHU_UIA_CLICK_ERROR:", "warn"),
            ):
                if line_strip.startswith(prefix):
                    self._in_code_block = False
                    self._log(
                        "  ⚠ " + line_strip.split(prefix, 1)[1].strip() + "\n", tag
                    )
                    return
            # Collapse: skip all other code body lines
            return

        if line_strip.startswith("FEISHU_TRACE:"):
            self._log("  " + line_strip + "\n", "muted")
            return

        # Settle delay
        if "等待 UI 稳定" in line:
            self._log("  " + line_strip + "\n", "normal")
            return

        # Model timing
        if "模型思考" in line:
            self._log(line, "normal")
            return

        # Signal lines
        if "EXEC_CODE_ERROR" in line or "Traceback" in line:
            tag = "warn"
        elif "REFLECTION" in line or "Response success" in line:
            tag = "normal"
        elif "SCREEN_INIT:" in line:
            tag = "normal"
        elif "ERROR" in line or "Error" in line:
            tag = "warn"
        else:
            tag = "normal"

        self._log(line, tag)

    def _load_command_history(self) -> list[str]:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, list):
                    values = [
                        item.strip()
                        for item in data
                        if isinstance(item, str) and item.strip()
                    ]
                    for command in CANDIDATE_COMMANDS:
                        if command not in values:
                            values.append(command)
                    return values
            except Exception as exc:
                _warn(f"load command history failed: {exc!r}")
        return list(CANDIDATE_COMMANDS)

    def _save_command_history(self, history: list[str]):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as handle:
                json.dump(history, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            _warn(f"save command history failed: {exc!r}")

    def _add_to_history(self, query: str):
        full = self._full_command_history
        if query in full:
            full.remove(query)
        full.insert(0, query)
        self._full_command_history = full[:50]
        self.cb_query["values"] = list(self._full_command_history)
        self._save_command_history(list(self._full_command_history))

    def _load_eval_suite_manifest(self) -> list[dict]:
        """Load test cases from the eval suite manifest."""
        if not os.path.exists(EVAL_SUITE_FILE):
            return []
        try:
            with open(EVAL_SUITE_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and isinstance(data.get("test_cases"), list):
                return [
                    tc
                    for tc in data["test_cases"]
                    if isinstance(tc, dict) and tc.get("instruction")
                ]
        except Exception as exc:
            _warn(f"load eval suite manifest failed: {exc!r}")
        return []

    def _insert_example_query(self):
        values = list(self.cb_query["values"])
        if values:
            self.v_query.set(values[0])

    def _show_example_dialog(self):
        """Open a pull+search dialog to select from eval suite and history."""
        dialog = tk.Toplevel(self.root)
        dialog.title("拉取示例指令")
        dialog.geometry("720x480")
        dialog.configure(bg=self.colors["panel"])
        dialog.transient(self.root)
        dialog.grab_set()

        # ── search bar ──
        search_frame = tk.Frame(dialog, bg=self.colors["panel"])
        search_frame.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(
            search_frame,
            text="搜索:",
            fg=self.colors["text"],
            bg=self.colors["panel"],
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left")
        search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_frame, textvariable=search_var, font=("Microsoft YaHei UI", 10)
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        search_entry.focus_set()

        # ── listbox with scrollbar ──
        list_frame = tk.Frame(dialog, bg=self.colors["panel"])
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        listbox = tk.Listbox(
            list_frame,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.colors["button_text"],
            font=("Microsoft YaHei UI", 9),
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ── load candidates from manifest + history ──
        manifest_entries: list[dict] = self._load_eval_suite_manifest()
        manifest_map: dict[str, dict] = {}
        candidate_texts: list[str] = []

        # Eval suite entries first (grouped by priority)
        for priority in ("high", "medium", "low"):
            for tc in manifest_entries:
                if tc.get("priority") != priority:
                    continue
                inst = tc["instruction"].strip()
                if inst not in manifest_map:
                    tag = f"[{tc['product'].upper()}] " if tc.get("product") else ""
                    label = f"{tag}{inst}"
                    manifest_map[label] = tc
                    candidate_texts.append(label)

        # History entries (filter out dupes that match manifest instructions)
        manifest_instructions = {tc["instruction"].strip() for tc in manifest_entries}
        for hist in self.cb_query["values"]:
            if hist not in manifest_instructions:
                candidate_texts.append(hist)

        def _refresh_list(*_args):
            query = search_var.get().strip().lower()
            listbox.delete(0, "end")
            for text in candidate_texts:
                if not query or query in text.lower():
                    listbox.insert("end", text)

        search_var.trace_add("write", _refresh_list)

        # ── selection → insert ──
        def _on_select():
            sel = listbox.curselection()
            if not sel:
                return
            text = listbox.get(sel[0])
            tc = manifest_map.get(text)
            if tc:
                self.v_query.set(tc["instruction"])
            else:
                self.v_query.set(text)
            dialog.destroy()

        def _on_double_click(_event):
            _on_select()

        listbox.bind("<Double-Button-1>", _on_double_click)
        listbox.bind("<Return>", lambda _e: _on_select())
        search_entry.bind("<Return>", lambda _e: _on_select())
        search_entry.bind(
            "<Down>", lambda _e: listbox.focus_set() or listbox.select_set(0)
        )

        # ── action buttons ──
        btn_frame = tk.Frame(dialog, bg=self.colors["panel"])
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(
            btn_frame,
            text="插入选中",
            style="Primary.TButton",
            command=_on_select,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            btn_frame,
            text="取消",
            style="Subtle.TButton",
            command=dialog.destroy,
        ).pack(side="right")

        _refresh_list()

        # ── keyboard: escape to close ──
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def _on_query_keyrelease(self, event):
        if event.keysym in (
            "Up",
            "Down",
            "Left",
            "Right",
            "Return",
            "Tab",
            "Escape",
            "Control_L",
            "Control_R",
            "Shift_L",
            "Shift_R",
            "Home",
            "End",
        ):
            if event.keysym == "Down" and self._suggestion_popup:
                self._suggestion_listbox.focus_set()
                self._suggestion_listbox.selection_set(0)
                return
            if event.keysym == "Escape":
                self._hide_suggestions()
                return
            return
        typed = self.v_query.get()
        if not typed:
            self._hide_suggestions()
            return
        lowered = typed.lower()
        filtered = [cmd for cmd in self._full_command_history if lowered in cmd.lower()]
        if filtered:
            self._show_suggestions(filtered)
        else:
            self._hide_suggestions()

    def _ensure_suggestion_popup(self):
        if self._suggestion_popup is not None:
            return
        popup = tk.Toplevel(self.root)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=self.colors["border"])
        listbox = tk.Listbox(
            popup,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.colors["button_text"],
            font=("Microsoft YaHei UI", 10),
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            height=6,
        )
        listbox.pack(padx=1, pady=1)
        listbox.bind("<Return>", lambda _e: self._accept_suggestion())
        listbox.bind("<Escape>", lambda _e: self._hide_suggestions())
        listbox.bind("<ButtonRelease-1>", lambda _e: self._accept_suggestion())
        listbox.bind("<Up>", lambda _e: self._suggestion_navigate(-1))
        listbox.bind("<Down>", lambda _e: self._suggestion_navigate(1))
        self._suggestion_popup = popup
        self._suggestion_listbox = listbox

    def _show_suggestions(self, items: list[str]):
        self._ensure_suggestion_popup()
        self._suggestion_listbox.delete(0, "end")
        for item in items:
            self._suggestion_listbox.insert("end", item)
        self._suggestion_listbox.selection_clear(0, "end")
        x = self.cb_query.winfo_rootx()
        y = self.cb_query.winfo_rooty() + self.cb_query.winfo_height()
        w = self.cb_query.winfo_width()
        self._suggestion_popup.geometry(f"{w}x{160}+{x}+{y}")
        self._suggestion_popup.deiconify()
        self._suggestion_popup.lift()

    def _hide_suggestions(self, *_args):
        if self._suggestion_popup:
            self._suggestion_popup.withdraw()

    def _accept_suggestion(self):
        sel = self._suggestion_listbox.curselection()
        if sel:
            text = self._suggestion_listbox.get(sel[0])
            self.v_query.set(text)
            self._hide_suggestions()
            self.cb_query.focus_set()
            self.cb_query.icursor(len(text))

    def _suggestion_navigate(self, delta):
        size = self._suggestion_listbox.size()
        if size == 0:
            return
        sel = self._suggestion_listbox.curselection()
        if not sel:
            self._suggestion_listbox.selection_set(0)
            return
        new_idx = (sel[0] + delta) % size
        self._suggestion_listbox.selection_clear(0, "end")
        self._suggestion_listbox.selection_set(new_idx)
        self._suggestion_listbox.see(new_idx)

    def _send_query(self):
        query = self.v_query.get().strip()
        if not query or not self.agent_ready:
            return
        self._log(f"\n▶ 指令：{query}\n", "query")
        self._write_stdin(query + "\n")
        self._add_to_history(query)
        self.v_query.set("")
        self.current_run_id = None
        self.current_run_dir = None
        self.btn_send.configure(state="disabled")
        self.cb_query.configure(state="disabled")
        self.btn_pull.configure(state="disabled")
        self.agent_ready = False
        self._set_status("处理中", "running", "任务已发送，等待下一轮 Query")

    def _write_stdin(self, text: str):
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write(text)
                self.process.stdin.flush()
            except Exception as exc:
                _warn(f"send command to agent failed: {exc!r}")

    def _clear_logs(self):
        for widget_name in ("log", "sop_log"):
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.configure(state="disabled")

    def _log(self, text: str, tag: str = "normal"):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_global_mousewheel(self, event):
        try:
            w = self.root.winfo_containing(event.x_root, event.y_root)
        except KeyError:
            return
        if isinstance(w, tk.Text):
            return
        while w is not None:
            if isinstance(w, tk.Canvas):
                w.yview_scroll(-1 * (event.delta // 120), "units")
                return
            w = w.master

    def _reload_sops(self):
        from sop_executor import list_sops

        for widget in self._sop_frame.winfo_children():
            widget.destroy()
        sops = list_sops()
        if not sops:
            ttk.Label(
                self._sop_frame,
                text="sops/ 目录为空，请在其中添加 JSON 文件",
                style="Muted.TLabel",
            ).pack(padx=14, pady=24)
            return
        for sop in sops:
            self._make_sop_card(sop)

    def _make_sop_card(self, sop: dict):
        card = ttk.LabelFrame(
            self._sop_frame,
            text=sop.get("name", "未命名"),
            style="Card.TLabelframe",
            padding=12,
        )
        card.pack(fill="x", padx=4, pady=6)
        card.columnconfigure(1, weight=1)
        desc = sop.get("description", "")
        if desc:
            ttk.Label(card, text=desc, style="Muted.TLabel", wraplength=760).grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
            )
        param_vars = {}
        for idx, param in enumerate(sop.get("params", []), start=1):
            ttk.Label(card, text=param["label"], style="App.TLabel").grid(
                row=idx, column=0, sticky="w", padx=(0, 10), pady=3
            )
            var = tk.StringVar()
            entry = ttk.Entry(card, textvariable=var)
            entry.grid(row=idx, column=1, sticky="ew", pady=3)
            placeholder = param.get("placeholder", "")
            if placeholder:
                entry.insert(0, placeholder)
            param_vars[param["name"]] = (var, placeholder)
        ttk.Button(
            card,
            text="立即执行",
            style="Primary.TButton",
            command=lambda payload=sop, vars_map=param_vars: self._run_sop(
                payload, vars_map
            ),
        ).grid(
            row=max(len(param_vars) + 1, 1),
            column=0,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )

    def _run_sop(self, sop: dict, param_vars: dict):
        params = {}
        for name, (var, placeholder) in param_vars.items():
            value = var.get().strip()
            params[name] = "" if value == placeholder else value
        missing = [
            p["label"]
            for p in sop.get("params", [])
            if not params.get(p["name"]) and not p.get("optional")
        ]
        if missing:
            messagebox.showwarning("缺少参数", f"请填写：{', '.join(missing)}")
            return
        self._sop_log_write(f"\n▶ 执行：{sop.get('name')}\n", "info")

        def worker():
            from sop_executor import run_sop

            try:
                run_sop(sop, params, log_fn=lambda msg: self._sop_log_write(msg + "\n"))
            except Exception as exc:
                self._sop_log_write(f"✗ 执行失败：{exc}\n", "err")

        threading.Thread(target=worker, daemon=True).start()

    def _sop_log_write(self, text: str, tag: str = "info"):
        self.sop_log.configure(state="normal")
        if "✅" in text or "完成" in text:
            tag = "ok"
        elif "✗" in text or "错误" in text or "失败" in text:
            tag = "err"
        self.sop_log.insert("end", text, tag)
        self.sop_log.see("end")
        self.sop_log.configure(state="disabled")

    def _format_replay_run_label(self, run: dict) -> str:
        updated = time.strftime("%m-%d %H:%M", time.localtime(run["updated_at"]))
        product = run.get("product") or "unknown"
        status = run.get("status") or "unknown"
        title = run.get("task_title") or run.get("run_id")
        return f"{updated} | {product} | {status} | {title}"

    def _reload_replay_runs(self):
        self._replay_runs = discover_semantic_replay_runs()
        self._selected_replay_index = None
        self.replay_listbox.delete(0, "end")
        if not self._replay_runs:
            self.v_replay_meta.set("未发现语义回放产物：artifacts/test_runs/*")
            self._set_replay_overview(
                "Replay Review Summary\n\nWarnings: no replay runs discovered\n"
            )
            self._set_replay_steps([])
            self._set_replay_preview(
                "还没有可观看的 replay_draft.md。\n\n"
                "运行 Feishu Agent 任务后，Track D 会在 artifacts/test_runs/<run_id>/ "
                "下生成 semantic_trace.json 和 replay_draft.md。"
            )
            return
        for run in self._replay_runs:
            self.replay_listbox.insert("end", self._format_replay_run_label(run))
        self.replay_listbox.selection_set(0)
        self._selected_replay_index = 0
        self._on_replay_select()

    def _selected_replay_run(self) -> dict | None:
        selection = self.replay_listbox.curselection()
        if selection:
            self._selected_replay_index = selection[0]
        index = self._selected_replay_index
        if index is None and len(self._replay_runs) == 1:
            index = 0
            self._selected_replay_index = 0
        if index is None:
            return None
        if index >= len(self._replay_runs):
            return None
        return self._replay_runs[index]

    def _set_replay_preview(self, text: str):
        self.replay_preview.configure(state="normal")
        self.replay_preview.delete("1.0", "end")
        self.replay_preview.insert("1.0", text)
        self.replay_preview.configure(state="disabled")

    def _set_replay_overview(self, text: str):
        self.replay_overview.configure(state="normal")
        self.replay_overview.delete("1.0", "end")
        self.replay_overview.insert("1.0", text)
        self.replay_overview.configure(state="disabled")

    def _set_replay_step_detail(self, text: str):
        self.replay_step_detail.configure(state="normal")
        self.replay_step_detail.delete("1.0", "end")
        self.replay_step_detail.insert("1.0", text)
        self.replay_step_detail.configure(state="disabled")

    def _set_replay_steps(self, steps: list[dict]):
        self._current_replay_steps = steps
        self.replay_step_listbox.delete(0, "end")
        if not steps:
            self._set_replay_step_detail("该运行没有可展示的 semantic_trace step。")
            return
        for ordinal, step in enumerate(steps, start=1):
            self.replay_step_listbox.insert(
                "end", format_replay_step_label(step, ordinal)
            )
        self.replay_step_listbox.selection_set(0)
        self._on_replay_step_select()

    def _on_replay_step_select(self, _event=None):
        selection = self.replay_step_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self._current_replay_steps):
            return
        self._set_replay_step_detail(
            render_replay_step_detail(self._current_replay_steps[index], index + 1)
        )

    def _on_replay_select(self, _event=None):
        run = self._selected_replay_run()
        if run is None:
            return
        self.v_replay_meta.set(
            f"run_id={run.get('run_id')} · product={run.get('product')} · "
            f"status={run.get('status')} · steps={run.get('trace_steps', 0)} · "
            f"screenshots={run.get('screenshots_count', 0)}"
        )
        steps = load_semantic_trace_steps(run.get("semantic_trace"))
        self._set_replay_overview(render_replay_review_summary(run, steps))
        self._set_replay_steps(steps)
        self._set_replay_preview(load_replay_artifact_preview(run))

    def _open_selected_replay_dir(self):
        run = self._selected_replay_run()
        if not run or not open_path_in_shell(run.get("run_dir")):
            messagebox.showwarning("无法打开", "请选择一个存在的运行目录。")

    def _open_selected_replay_draft(self):
        run = self._selected_replay_run()
        if not run or not open_path_in_shell(select_replay_preview_path(run)):
            messagebox.showwarning(
                "无法打开", "该运行没有 replay_draft.md 或 report.md。"
            )

    def _open_selected_screenshots_dir(self):
        run = self._selected_replay_run()
        if not run or not open_path_in_shell(run.get("screenshots_dir")):
            messagebox.showwarning("无法打开", "该运行没有 screenshots 目录。")

    def _copy_replay_review_summary(self):
        run = self._selected_replay_run()
        if not run:
            messagebox.showwarning("无法复制", "请选择一个运行记录。")
            return
        steps = load_semantic_trace_steps(run.get("semantic_trace"))
        self.root.clipboard_clear()
        self.root.clipboard_append(render_replay_review_summary(run, steps))
        self._set_status("已复制", "saved", "语义回放审阅摘要已复制到剪贴板")

    def _save_config(self):
        self._persist_current_forms()
        try:
            gw = int(self.v_gw.get().strip())
            gh = int(self.v_gh.get().strip())
            self.cfg.setdefault("grounding_overrides", {})
            self.cfg["grounding_overrides"][self._active_ground_key] = {
                "width": gw,
                "height": gh,
            }
        except ValueError:
            pass
        save_config(self.cfg)
        self._set_status("配置已保存", "saved", "当前 provider 与运行参数已落盘")

    def _on_close(self):
        self._stop_agent()
        self._stop_dashboard_server()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Launcher().run()
