"""Local read-only dashboard server for Feishu evaluation artifacts."""

from __future__ import annotations

import html
import hashlib
import json
import mimetypes
import re
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from gui_agents.feishu.reports.evaluation_aggregator import (
    build_evaluation_dashboard_html,
    build_evaluation_summary,
    discover_run_summaries,
    write_evaluation_report,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "test_runs"
DEFAULT_EVALUATION_DIR = REPO_ROOT / "artifacts" / "evaluation"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_EMPTY_LABELS = {"", "unknown", "none", "null", "n/a", "-"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _safe_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _safe_duration(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{numeric:.2f}s" if numeric < 10 else f"{numeric:.1f}s"


def _label(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if text.lower() in _EMPTY_LABELS:
        return default
    return text


def _summary_result(summary: dict[str, Any]) -> str:
    result = str(summary.get("result") or "").strip().lower()
    if result and result not in _EMPTY_LABELS:
        return result
    status = str(summary.get("status") or "not_recorded").strip().lower()
    if status in {"completed", "passed", "success"}:
        return "passed"
    if status in {"failed", "error"}:
        return "failed"
    return status or "not_recorded"


def _short_run_id(run_id: Any) -> str:
    text = str(run_id or "ad_hoc_run")
    parts = [item for item in text.split("_") if item]
    return parts[-1] if parts else text


def _run_dir(run: dict[str, Any]) -> Path:
    return Path(str(run["summary_path"])).resolve().parent


def _relative_run_file(run_dir: Path, path_value: str | None) -> str | None:
    if not path_value:
        return None
    try:
        return Path(path_value).resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return None


def _run_file_href(run_id: str, relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return f"/runs/{quote(run_id)}/files/{quote(relative_path, safe='/')}"


def _screenshot_files(run_dir: Path) -> list[Path]:
    screenshot_dir = run_dir / "screenshots"
    if not screenshot_dir.exists() or not screenshot_dir.is_dir():
        return []
    return sorted(item for item in screenshot_dir.iterdir() if item.is_file())


def _markdown_to_html(markdown: str) -> str:
    """Convert a small report markdown subset into safe HTML."""

    lines: list[str] = []
    in_code = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                lines.append("</code></pre>")
                in_code = False
            else:
                lines.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            lines.append(_escape(line))
            continue
        if not line:
            lines.append("")
            continue
        if line.startswith("# "):
            lines.append(f"<h1>{_escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{_escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            lines.append(f"<h3>{_escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            lines.append(f'<p class="bullet">{_inline_markdown(line[2:].strip())}</p>')
        else:
            lines.append(f"<p>{_inline_markdown(line)}</p>")
    if in_code:
        lines.append("</code></pre>")
    return "\n".join(lines)


def _inline_markdown(text: str) -> str:
    escaped = _escape(text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <style>
    :root {{
      --page: #f5f8ff;
      --paper: #ffffff;
      --ink: #142033;
      --muted: #64748b;
      --line: rgba(47, 111, 235, 0.1);
      --feishu: #1f7aff;
      --feishu-deep: #1456d9;
      --cyan: #00b8d9;
      --success: #12b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --soft-blue: #eaf2ff;
      --radius: 12px;
      --shadow-sm: 0 1px 3px rgba(20, 64, 153, 0.08);
      --shadow: 0 4px 16px rgba(20, 64, 153, 0.08), 0 1px 4px rgba(20, 64, 153, 0.06);
      --shadow-lg: 0 12px 32px rgba(20, 64, 153, 0.1), 0 2px 8px rgba(20, 64, 153, 0.06);
      --body-font: "Microsoft YaHei UI", "Aptos", "Segoe UI Variable Text", sans-serif;
      --mono-font: "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background: linear-gradient(180deg, #fafcff 0%, var(--page) 40%, #f0f4ff 100%);
      font-family: var(--body-font);
      -webkit-font-smoothing: antialiased;
    }}
    .shell {{
      width: min(1180px, calc(100vw - 40px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      padding: 32px 36px;
      margin-bottom: 24px;
      border-radius: var(--radius);
      background: linear-gradient(135deg, #ffffff 0%, #f6f9ff 100%);
      border: 1px solid rgba(31, 122, 255, 0.1);
      box-shadow: var(--shadow-lg);
    }}
    .hero::before {{
      content: "";
      position: absolute;
      top: 0; left: 0;
      width: 4px;
      height: 64px;
      background: linear-gradient(180deg, var(--feishu), var(--cyan));
      border-radius: 0 0 4px 0;
    }}
    .hero h1 {{
      margin: 0;
      max-width: 860px;
      color: var(--ink);
      font-size: clamp(1.6rem, 3.5vw, 2.4rem);
      font-weight: 700;
      line-height: 1.15;
      letter-spacing: -0.01em;
    }}
    .hero p, .muted {{ color: var(--muted); line-height: 1.6; font-size: 0.94rem; }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }}
    .hero-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 30px;
      padding: 5px 10px;
      border-radius: 999px;
      color: var(--feishu-deep);
      background: rgba(31, 122, 255, 0.08);
      border: 1px solid rgba(31, 122, 255, 0.12);
      font-size: 0.78rem;
      font-weight: 600;
    }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }}
    a.button, button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      min-height: 36px;
      border: 1px solid rgba(31, 122, 255, 0.18);
      border-radius: 999px;
      padding: 6px 16px;
      color: var(--feishu-deep);
      background: #ffffff;
      text-decoration: none;
      font: inherit;
      font-size: 0.82rem;
      font-weight: 500;
      transition: all 180ms ease;
    }}
    a.button:hover, button:hover {{
      color: #ffffff;
      background: var(--feishu);
      border-color: var(--feishu);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(31, 122, 255, 0.25);
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .card {{
      padding: 22px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow);
    }}
    .card strong {{
      display: block;
      color: var(--feishu-deep);
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .card small, .label {{
      color: var(--muted);
      font-size: 0.73rem;
      font-weight: 500;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .icon {{
      display: inline-flex;
      width: 34px;
      height: 34px;
      align-items: center;
      justify-content: center;
      border-radius: 10px;
      color: var(--feishu);
      background: rgba(31, 122, 255, 0.08);
      border: 1px solid rgba(31, 122, 255, 0.1);
      flex: 0 0 auto;
    }}
    .icon svg {{
      width: 18px;
      height: 18px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .quality-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .quality-card {{
      min-height: 138px;
      padding: 18px;
      border-radius: var(--radius);
      background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow-sm);
      display: grid;
      gap: 12px;
      align-content: start;
    }}
    .quality-card header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .quality-card strong {{
      font-size: 1.35rem;
      color: var(--ink);
      letter-spacing: 0;
    }}
    .quality-card p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.5;
    }}
    .distribution {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .dist-box {{
      padding: 16px;
      border-radius: var(--radius);
      background: rgba(234, 242, 255, 0.38);
      border: 1px solid rgba(31, 122, 255, 0.08);
    }}
    .dist-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 80px 36px;
      gap: 10px;
      align-items: center;
      margin-top: 10px;
      font-size: 0.82rem;
    }}
    .dist-row .bar {{
      height: 7px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(31, 122, 255, 0.1);
    }}
    .dist-row .bar i {{
      display: block;
      height: 100%;
      width: var(--value);
      border-radius: inherit;
      background: linear-gradient(90deg, var(--feishu), var(--cyan));
    }}
    .runs {{ display: grid; gap: 10px; margin-top: 16px; }}
    .run {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 120px 110px 86px auto;
      gap: 14px;
      align-items: center;
      padding: 14px 18px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      transition: box-shadow 160ms ease;
    }}
    .run:hover {{
      box-shadow: var(--shadow);
    }}
    .pill {{
      width: fit-content;
      min-width: 80px;
      padding: 5px 12px;
      border-radius: 999px;
      color: #065f46;
      background: rgba(18, 185, 129, 0.12);
      text-align: center;
      font-size: 0.75rem;
      font-weight: 500;
    }}
    .pill.failed {{ color: #9f1239; background: rgba(239, 68, 68, 0.12); }}
    .report {{
      padding: 28px 32px;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow);
    }}
    .report h1 {{
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .report h2 {{
      margin-top: 24px;
      color: var(--feishu-deep);
      font-size: 1.2rem;
      font-weight: 600;
    }}
    .report code {{
      color: var(--feishu-deep);
      background: rgba(31,122,255,.06);
      padding: 2px 6px;
      border-radius: 6px;
      font-size: 0.9em;
    }}
    .report pre {{
      overflow-x: auto;
      padding: 16px;
      border-radius: 8px;
      background: rgba(234,242,255,.5);
      border: 1px solid rgba(31, 122, 255, 0.06);
    }}
    .bullet {{
      padding-left: 18px;
      position: relative;
      line-height: 1.6;
    }}
    .bullet::before {{
      content: "";
      position: absolute;
      left: 0;
      top: 0.7em;
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: var(--cyan);
    }}
    .section-title {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 16px;
    }}
    .section-title h2 {{
      margin: 0;
      font-size: 1.15rem;
      font-weight: 600;
      letter-spacing: -0.01em;
    }}
    .section-title .label {{
      color: var(--muted);
      font-size: 0.75rem;
    }}
    .report-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}
    .step-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .step-card {{
      overflow: hidden;
      border-radius: var(--radius);
      background: #ffffff;
      border: 1px solid rgba(31, 122, 255, 0.08);
      box-shadow: var(--shadow-sm);
      transition: box-shadow 200ms ease, transform 200ms ease;
    }}
    .step-card:hover {{
      box-shadow: var(--shadow);
      transform: translateY(-2px);
    }}
    .step-shot {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: cover;
      background: linear-gradient(135deg, rgba(31, 122, 255, 0.06), rgba(0, 184, 217, 0.06));
      border-bottom: 1px solid rgba(31, 122, 255, 0.06);
    }}
    .shot-empty {{
      display: grid;
      place-items: center;
      aspect-ratio: 16 / 10;
      color: var(--muted);
      font-size: 0.82rem;
      background: rgba(234, 242, 255, 0.4);
    }}
    .step-copy {{ padding: 18px; display: grid; gap: 10px; }}
    .step-head {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
    }}
    .step-head h3 {{
      margin: 0;
      font-size: 1.1rem;
      font-weight: 600;
    }}
    .meta {{
      display: grid;
      gap: 8px;
    }}
    .meta-line {{
      display: grid;
      gap: 2px;
      padding-top: 8px;
      border-top: 1px solid rgba(31, 122, 255, 0.06);
    }}
    .meta-line span {{
      color: var(--muted);
      font-size: 0.7rem;
      font-weight: 500;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .artifact-list {{
      display: grid;
      gap: 10px;
    }}
    .artifact-item {{
      padding: 14px 16px;
      border-radius: 8px;
      background: rgba(234, 242, 255, 0.4);
      border: 1px solid rgba(31, 122, 255, 0.06);
    }}
    .artifact-item.with-icon {{
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
    }}
    .artifact-item code {{
      display: inline-block;
      margin-top: 6px;
      word-break: break-all;
      font-size: 0.82rem;
    }}
    @media (max-width: 780px) {{
      .shell {{ width: min(100vw - 32px, 1180px); }}
      .hero {{ padding: 24px; }}
      .report {{ padding: 20px; }}
      .metric-grid, .grid, .run, .report-grid, .quality-grid, .distribution, .step-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">{body}</main>
</body>
</html>
""".encode(
        "utf-8"
    )


def discover_report_runs(artifact_root: str | Path) -> list[dict[str, Any]]:
    root = Path(artifact_root)
    if not root.exists():
        return []
    runs: list[dict[str, Any]] = []
    for summary_path in sorted(root.glob("*/summary.json")):
        run_dir = summary_path.parent
        summary = _read_json(summary_path)
        report_path = run_dir / "report.md"
        replay_path = run_dir / "replay_draft.md"
        trace_path = run_dir / "semantic_trace.json"
        manifest = summary.get("artifact_manifest", {})
        screenshot_files = _screenshot_files(run_dir)
        final_screenshot = None
        if isinstance(manifest, dict):
            final_screenshot = manifest.get("final_screenshot")
        if not final_screenshot and screenshot_files:
            final_screenshot = str(screenshot_files[-1])
        runs.append(
            {
                "run_id": str(summary.get("run_id") or run_dir.name),
                "task_id": _label(summary.get("task_id"), "ad_hoc_task"),
                "product": _label(summary.get("product"), "general"),
                "priority": _label(summary.get("priority"), "medium"),
                "complexity": _label(summary.get("complexity"), "medium"),
                "status": _label(summary.get("status"), "not_recorded"),
                "result": _summary_result(summary),
                "duration_sec": summary.get("duration_sec"),
                "observed_steps": summary.get("observed_steps", summary.get("steps")),
                "step_pass_rate": summary.get("step_pass_rate"),
                "step_efficiency": summary.get("step_efficiency"),
                "partial_credit": summary.get("partial_credit"),
                "assertion_pass_rate": summary.get("assertion_pass_rate"),
                "screenshot_count": summary.get(
                    "screenshot_count", len(screenshot_files)
                ),
                "reflection_count": summary.get("reflection_count", 0),
                "redundant_action_rate": summary.get("redundant_action_rate", 0.0),
                "locator_stats": summary.get("locator_stats", {}),
                "completion_signal": _label(
                    summary.get("completion_signal"),
                    f"status_{_summary_result(summary)}",
                ),
                "exec_error_count": summary.get("exec_error_count", 0),
                "exec_errors": summary.get("exec_errors", []),
                "action_type_counts": summary.get("action_type_counts", {}),
                "failure_type": summary.get("failure_type"),
                "failure_reason": summary.get("failure_reason"),
                "summary_path": str(summary_path),
                "run_dir": str(run_dir),
                "report_path": str(report_path) if report_path.exists() else None,
                "replay_path": str(replay_path) if replay_path.exists() else None,
                "semantic_trace_path": str(trace_path) if trace_path.exists() else None,
                "final_screenshot": final_screenshot,
                "step_artifacts": summary.get("step_artifacts", []),
                "assertions": summary.get("assertions", []),
                "artifact_manifest": manifest if isinstance(manifest, dict) else {},
            }
        )
    return runs


def _path_stat_fields(path: Path) -> tuple[int, int]:
    if not str(path) or str(path) == ".":
        return 0, 0
    try:
        stat = path.stat()
    except OSError:
        return 0, 0
    return stat.st_mtime_ns, stat.st_size


def _sort_runs_newest_first(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(run: dict[str, Any]) -> tuple[int, str]:
        summary_path = Path(str(run.get("summary_path") or ""))
        mtime_ns, _ = _path_stat_fields(summary_path)
        return (mtime_ns, str(run.get("run_id") or ""))

    return sorted(runs, key=_key, reverse=True)


def discover_pending_runs(artifact_root: str | Path) -> list[dict[str, Any]]:
    root = Path(artifact_root)
    if not root.exists():
        return []

    pending: list[dict[str, Any]] = []
    tracked_files = (
        "report.md",
        "actions.jsonl",
        "semantic_trace.json",
        "replay_draft.md",
    )
    for run_dir in root.iterdir():
        if not run_dir.is_dir():
            continue
        if (run_dir / "summary.json").exists():
            continue

        screenshot_files = _screenshot_files(run_dir)
        present_artifacts: list[str] = []
        stat_targets: list[Path] = []
        if screenshot_files:
            present_artifacts.append("screenshots")
            stat_targets.extend(screenshot_files)

        for filename in tracked_files:
            target = run_dir / filename
            if target.exists() and target.is_file():
                present_artifacts.append(filename)
                stat_targets.append(target)

        if not present_artifacts:
            continue

        updated_at_ns = max(
            [_path_stat_fields(path)[0] for path in stat_targets]
            + [_path_stat_fields(run_dir)[0]]
        )
        pending.append(
            {
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "screenshot_count": len(screenshot_files),
                "present_artifacts": present_artifacts,
                "missing_artifacts": ["summary.json"],
                "updated_at_ns": updated_at_ns,
            }
        )

    return sorted(
        pending,
        key=lambda item: (int(item.get("updated_at_ns", 0)), str(item.get("run_id"))),
        reverse=True,
    )


def build_dashboard_payload(artifact_root: str | Path) -> dict[str, Any]:
    summaries = discover_run_summaries(artifact_root)
    evaluation = build_evaluation_summary(summaries)
    runs = _sort_runs_newest_first(list(evaluation.get("runs", [])))
    pending_runs = discover_pending_runs(artifact_root)

    snapshot_components = {
        "runs": [
            {
                "run_id": run.get("run_id"),
                "summary_path": run.get("summary_path"),
                "summary_stat": _path_stat_fields(
                    Path(str(run.get("summary_path") or ""))
                ),
            }
            for run in runs
        ],
        "pending_runs": [
            {
                "run_id": run.get("run_id"),
                "updated_at_ns": run.get("updated_at_ns"),
                "screenshot_count": run.get("screenshot_count"),
                "present_artifacts": run.get("present_artifacts"),
            }
            for run in pending_runs
        ],
    }
    snapshot_id = hashlib.sha1(
        json.dumps(snapshot_components, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()[:16]

    evaluation["runs"] = runs
    evaluation["pending_runs"] = pending_runs
    evaluation["pending_run_count"] = len(pending_runs)
    evaluation["dashboard_snapshot_id"] = snapshot_id
    return evaluation


def _run_index(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(run["run_id"]): run for run in runs}


def _step_evidence_cards(run: dict[str, Any]) -> str:
    run_id = str(run["run_id"])
    run_dir = _run_dir(run)
    step_artifacts = run.get("step_artifacts") or []
    if step_artifacts:
        cards: list[str] = []
        for index, step in enumerate(step_artifacts, start=1):
            screenshot_url = _run_file_href(
                run_id,
                _relative_run_file(run_dir, step.get("screenshot")),
            )
            status = _label(step.get("result") or step.get("status"), "not_recorded")
            status_class = " failed" if status != "passed" else ""
            image_html = (
                f'<img class="step-shot" src="{_escape(screenshot_url)}" alt="{_escape(step.get("step_id") or f"step-{index}")} screenshot">'
                if screenshot_url
                else '<div class="step-shot shot-empty">未记录截图</div>'
            )
            cards.append(
                '<article class="step-card">'
                f"{image_html}"
                '<div class="step-copy">'
                '<div class="step-head">'
                f'<h3>{_escape(step.get("step_id") or f"step-{index}")}</h3>'
                f'<span class="pill{status_class}">{_escape(status)}</span>'
                "</div>"
                '<div class="meta">'
                f'<div class="meta-line"><span>Stage</span><strong>{_escape(step.get("stage") or "-")}</strong></div>'
                f'<div class="meta-line"><span>Action</span><strong>{_escape(step.get("action") or "-")}</strong></div>'
                f'<div class="meta-line"><span>Assertion</span><strong>{_escape(step.get("assertion") or "-")}</strong></div>'
                f'<div class="meta-line"><span>Failure</span><strong>{_escape(step.get("failure_reason") or "-")}</strong></div>'
                "</div>"
                "</div>"
                "</article>"
            )
        return "".join(cards)

    screenshot_files = _screenshot_files(run_dir)
    if not screenshot_files:
        return '<p class="muted">本次运行未记录截图。</p>'

    cards = []
    for index, screenshot_path in enumerate(screenshot_files, start=1):
        relative_path = screenshot_path.relative_to(run_dir).as_posix()
        screenshot_url = _run_file_href(run_id, relative_path)
        cards.append(
            '<article class="step-card">'
            f'<img class="step-shot" src="{_escape(screenshot_url)}" alt="step screenshot {index}">'
            '<div class="step-copy">'
            '<div class="step-head">'
            f'<h3>Step {index}</h3><span class="pill">{_escape(screenshot_path.name)}</span>'
            "</div>"
            '<div class="meta">'
            f'<div class="meta-line"><span>Artifact</span><strong>{_escape(relative_path)}</strong></div>'
            "</div>"
            "</div>"
            "</article>"
        )
    return "".join(cards)


def _artifact_items(run: dict[str, Any]) -> str:
    run_id = str(run["run_id"])
    run_dir = _run_dir(run)
    manifest = run.get("artifact_manifest") or {}
    items = {
        "Summary": run.get("summary_path"),
        "Report": run.get("report_path"),
        "Replay Draft": run.get("replay_path"),
        "Semantic Trace": run.get("semantic_trace_path"),
        "Final Screenshot": run.get("final_screenshot"),
    }
    if isinstance(manifest, dict):
        items["Actions"] = manifest.get("actions")

    rendered: list[str] = []
    for label, path_value in items.items():
        relative_path = (
            _relative_run_file(run_dir, str(path_value)) if path_value else None
        )
        href = _run_file_href(run_id, relative_path)
        link_html = (
            f'<a class="button" href="{_escape(href)}">{_escape(label)}</a>'
            if href
            else f'<span class="muted">{_escape(label)} unavailable</span>'
        )
        rendered.append(
            '<div class="artifact-item">'
            f'<div class="label">{_escape(label)}</div>'
            f"{link_html}"
            f'<code>{_escape(path_value or "-")}</code>'
            "</div>"
        )
    return "".join(rendered)


def _icon(name: str) -> str:
    paths = {
        "check": '<path d="M20 6 9 17l-5-5"></path>',
        "clock": '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>',
        "steps": '<path d="M4 7h16"></path><path d="M4 12h10"></path><path d="M4 17h16"></path>',
        "camera": '<path d="M14.5 5 13 3H9L7.5 5H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle>',
        "target": '<circle cx="12" cy="12" r="9"></circle><circle cx="12" cy="12" r="4"></circle><path d="M12 2v3"></path><path d="M12 19v3"></path><path d="M2 12h3"></path><path d="M19 12h3"></path>',
        "repeat": '<path d="m17 2 4 4-4 4"></path><path d="M3 11V9a3 3 0 0 1 3-3h15"></path><path d="m7 22-4-4 4-4"></path><path d="M21 13v2a3 3 0 0 1-3 3H3"></path>',
        "terminal": '<path d="m4 17 6-5-6-5"></path><path d="M12 19h8"></path>',
        "spark": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"></path><path d="M19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8z"></path>',
        "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6"></path>',
    }
    return (
        f'<span class="icon" aria-hidden="true"><svg viewBox="0 0 24 24">'
        f'{paths.get(name, paths["file"])}</svg></span>'
    )


def _quality_card(icon: str, label: str, value: str, caption: str) -> str:
    return (
        '<article class="quality-card">'
        f'<header><span class="label">{_escape(label)}</span>{_icon(icon)}</header>'
        f"<strong>{_escape(value)}</strong>"
        f"<p>{_escape(caption)}</p>"
        "</article>"
    )


def _distribution_rows(items: dict[str, Any]) -> str:
    if not isinstance(items, dict) or not items:
        return '<p class="muted">未记录分布数据。</p>'
    numeric_items = [
        (str(label), int(float(value or 0))) for label, value in sorted(items.items())
    ]
    max_value = max([value for _, value in numeric_items] + [1])
    return "".join(
        '<div class="dist-row">'
        f"<strong>{_escape(label)}</strong>"
        '<span class="bar">'
        f'<i style="--value: {max(round((value / max_value) * 100), 3)}%"></i>'
        "</span>"
        f"<span>{_escape(value)}</span>"
        "</div>"
        for label, value in numeric_items
    )


def _exec_error_items(run: dict[str, Any]) -> str:
    errors = run.get("exec_errors")
    if not isinstance(errors, list) or not errors:
        return (
            '<div class="artifact-item with-icon">'
            f'{_icon("check")}'
            '<div><div class="label">Exec Errors</div>'
            "<strong>无执行异常</strong><code>runtime execution clean</code></div>"
            "</div>"
        )
    rendered: list[str] = []
    for item in errors[:6]:
        if not isinstance(item, dict):
            continue
        rendered.append(
            '<div class="artifact-item with-icon">'
            f'{_icon("terminal")}'
            "<div>"
            f'<div class="label">{_escape(item.get("step_id") or "runtime_step")}</div>'
            f'<strong>{_escape(item.get("action") or "exec")}</strong>'
            f'<code>{_escape(item.get("failure_reason") or item.get("status") or "error")}</code>'
            "</div></div>"
        )
    return "".join(rendered) or '<p class="muted">无执行异常。</p>'


def _quality_signal_section(run: dict[str, Any], summary: dict[str, Any]) -> str:
    locator = run.get("locator_stats")
    locator = locator if isinstance(locator, dict) else {}
    locator_match = _safe_percent(locator.get("match_rate"))
    cards = [
        _quality_card(
            "steps",
            "Step Efficiency",
            _safe_percent(run.get("step_efficiency")),
            "估计步数与实际观测步数的接近程度，越高说明路径越短。",
        ),
        _quality_card(
            "spark",
            "Partial Credit",
            _safe_percent(run.get("partial_credit")),
            "综合步骤通过率与断言通过率，用于解释失败运行的完成程度。",
        ),
        _quality_card(
            "repeat",
            "Reflection",
            str(run.get("reflection_count", 0)),
            "AgentS3 运行中记录到的反思/自愈介入次数。",
        ),
        _quality_card(
            "repeat",
            "Redundant Action",
            _safe_percent(run.get("redundant_action_rate")),
            "相邻重复动作占比，越低说明绕路越少。",
        ),
        _quality_card(
            "target",
            "Locator Match",
            f'{locator_match} ({locator.get("matched", 0)} / {locator.get("total", 0)})',
            "运行步骤中定位记录的匹配情况；历史产物缺失时显示为未记录。",
        ),
        _quality_card(
            "terminal",
            "Exec Errors",
            str(run.get("exec_error_count", 0)),
            "执行阶段异常数量，包含失败动作与 runtime failure。",
        ),
        _quality_card(
            "check",
            "Completion Signal",
            _label(run.get("completion_signal"), "not_recorded"),
            "最后一次动作或最终状态派生出的完成信号。",
        ),
        _quality_card(
            "camera",
            "Evidence Chain",
            str(run.get("screenshot_count", 0)),
            "截图、summary、actions、report 等审阅证据的基础链路。",
        ),
        _quality_card(
            "file",
            "Priority / Complexity",
            f'{_label(summary.get("priority") or run.get("priority"), "medium")} / {_label(summary.get("complexity") or run.get("complexity"), "medium")}',
            "按任务元数据或运行规模派生，用于看板分组比较。",
        ),
    ]
    action_counts = run.get("action_type_counts")
    strategy_counts = locator.get("strategy_counts")
    return (
        '<section class="report" style="margin-top: 18px;">'
        '<div class="section-title">'
        "<h2>过程质量 / Process Quality</h2>"
        '<span class="label">efficiency, recovery, locator, execution</span>'
        "</div>"
        f'<div class="quality-grid">{"".join(cards)}</div>'
        '<div class="distribution">'
        '<div class="dist-box"><div class="label">Action Distribution</div>'
        f"{_distribution_rows(action_counts if isinstance(action_counts, dict) else {})}"
        "</div>"
        '<div class="dist-box"><div class="label">Locator Strategy</div>'
        f"{_distribution_rows(strategy_counts if isinstance(strategy_counts, dict) else {})}"
        "</div>"
        "</div>"
        "</section>"
    )


def _build_run_report_html(run: dict[str, Any]) -> bytes:
    result = _label(run.get("result"), "not_recorded")
    result_class = " failed" if result != "passed" else ""
    run_id = str(run.get("run_id") or "ad_hoc_run")
    compact_run_id = _short_run_id(run_id)
    summary = _read_json(Path(str(run["summary_path"])))
    raw_report = ""
    if run.get("report_path"):
        raw_report = Path(str(run["report_path"])).read_text(
            encoding="utf-8", errors="replace"
        )
    markdown_appendix = _markdown_to_html(
        raw_report or "# Feishu Run Report\n\nNo markdown report recorded."
    )
    body = f"""
    <section class="hero">
      <h1>运行报告 / {_escape(compact_run_id)}</h1>
      <p>完整运行 ID：<code>{_escape(run_id)}</code>。本页用于审阅步骤证据、产物链接和派生评测指标，不执行回放。</p>
      <div class="hero-meta">
        <span class="hero-chip">{_icon("file")}{_escape(_label(run.get("product"), "general"))}</span>
        <span class="hero-chip">{_icon("spark")}{_escape(_label(run.get("priority"), "medium"))}</span>
        <span class="hero-chip">{_icon("steps")}{_escape(_label(run.get("complexity"), "medium"))}</span>
        <span class="hero-chip">{_icon("check")}{_escape(_label(run.get("completion_signal"), "not_recorded"))}</span>
      </div>
      <div class="nav">
        <a class="button" href="/dashboard">返回看板</a>
        <a class="button" href="/runs/{_escape(run_id)}/summary">Summary JSON</a>
        <a class="button" href="/runs/{_escape(run_id)}/replay">回放草稿</a>
      </div>
    </section>
    <section class="report-grid">
      <article class="card">{_icon("check")}<span class="label">Result</span><strong>{_escape(result)}</strong><span class="pill{result_class}">{_escape(run.get("status"))}</span></article>
      <article class="card">{_icon("clock")}<span class="label">Duration</span><strong>{_escape(_safe_duration(run.get("duration_sec")))}</strong><small>wall clock</small></article>
      <article class="card">{_icon("steps")}<span class="label">Step Pass</span><strong>{_escape(_safe_percent(run.get("step_pass_rate")))}</strong><small>{_escape(run.get("observed_steps"))} observed steps</small></article>
      <article class="card">{_icon("target")}<span class="label">Assertion Pass</span><strong>{_escape(_safe_percent(run.get("assertion_pass_rate")))}</strong><small>{_escape(len(summary.get("assertions", [])))} assertions</small></article>
      <article class="card">{_icon("camera")}<span class="label">Screenshots</span><strong>{_escape(run.get("screenshot_count"))}</strong><small>review evidence</small></article>
    </section>
    {_quality_signal_section(run, summary)}
    <section class="report" style="margin-top: 18px;">
      <div class="section-title">
        <h2>执行异常 / Exec Errors</h2>
        <span class="label">runtime failure evidence</span>
      </div>
      <div class="artifact-list">
        {_exec_error_items(run)}
      </div>
    </section>
    <section class="report">
      <div class="section-title">
        <h2>步骤证据 / Step Evidence</h2>
        <span class="label">per-step screenshot gallery</span>
      </div>
      <div class="step-grid">
        {_step_evidence_cards(run)}
      </div>
    </section>
    <section class="report" style="margin-top: 18px;">
      <div class="section-title">
        <h2>Artifacts</h2>
        <span class="label">review bundle</span>
      </div>
      <div class="artifact-list">
        {_artifact_items(run)}
      </div>
    </section>
    <section class="report" style="margin-top: 18px;">
      <div class="section-title">
        <h2>Assertions</h2>
        <span class="label">case-level outcomes</span>
      </div>
      {''.join(
          '<div class="artifact-item">'
          f'<div class="label">{_escape(item.get("name"))}</div>'
          f'<strong>{_escape("passed" if item.get("passed") else "failed")}</strong>'
          f'<code>{_escape(item.get("failure_reason") or "-")}</code>'
          '</div>'
          for item in summary.get("assertions", [])
      ) or '<p class="muted">No assertion results recorded.</p>'}
    </section>
    <section class="report" style="margin-top: 18px;">
      <div class="section-title">
        <h2>Markdown Appendix</h2>
        <span class="label">raw report.md</span>
      </div>
      {markdown_appendix}
    </section>
    """
    return _page(f"Report {run.get('run_id')}", body)


def build_portal_html(
    *,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    evaluation_dir: str | Path = DEFAULT_EVALUATION_DIR,
) -> bytes:
    """Build the legacy portal payload as the unified dashboard HTML."""

    write_evaluation_report(artifact_root, evaluation_dir)
    payload = build_dashboard_payload(artifact_root)
    return build_evaluation_dashboard_html(payload).encode("utf-8")


@dataclass
class DashboardServerHandle:
    server: ThreadingHTTPServer
    thread: threading.Thread
    url: str

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


class FeishuDashboardRequestHandler(BaseHTTPRequestHandler):
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    evaluation_dir: Path = DEFAULT_EVALUATION_DIR

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle_request(send_body=False)

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "Read-only dashboard server")

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _handle_request(self, *, send_body: bool) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in {"", "/"}:
            self._redirect("/dashboard", send_body=send_body)
            return
        if path == "/dashboard":
            self._send_bytes(
                build_portal_html(
                    artifact_root=self.artifact_root,
                    evaluation_dir=self.evaluation_dir,
                ),
                "text/html; charset=utf-8",
                send_body=send_body,
            )
            return
        if path == "/api/evaluation-summary":
            write_evaluation_report(self.artifact_root, self.evaluation_dir)
            payload = build_dashboard_payload(self.artifact_root)
            self._send_bytes(
                (
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                ).encode("utf-8"),
                "application/json; charset=utf-8",
                send_body=send_body,
            )
            return
        if path.startswith("/runs/"):
            self._serve_run_path(path, send_body=send_body)
            return
        if path.startswith("/artifacts/evaluation/"):
            relative = path.removeprefix("/artifacts/evaluation/")
            self._serve_safe_file(self.evaluation_dir, relative, send_body=send_body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _redirect(self, location: str, *, send_body: bool) -> None:
        payload = b""
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def _serve_run_path(self, path: str, *, send_body: bool) -> None:
        parts = [item for item in path.split("/") if item]
        if len(parts) < 3:
            self.send_error(HTTPStatus.NOT_FOUND, "Invalid run path")
            return
        run_id = parts[1]
        artifact = parts[2]
        run = _run_index(discover_report_runs(self.artifact_root)).get(run_id)
        if not run:
            self.send_error(HTTPStatus.NOT_FOUND, "Run not found")
            return
        if artifact == "files":
            if len(parts) < 4:
                self.send_error(HTTPStatus.NOT_FOUND, "Missing file path")
                return
            relative = "/".join(parts[3:])
            self._serve_safe_file(
                _run_dir(run),
                relative,
                send_body=send_body,
            )
            return
        if len(parts) != 3:
            self.send_error(HTTPStatus.NOT_FOUND, "Invalid run path")
            return
        if artifact == "report":
            self._send_bytes(
                _build_run_report_html(run),
                "text/html; charset=utf-8",
                send_body=send_body,
            )
            return
        if artifact == "replay":
            replay_path = run.get("replay_path")
            if not replay_path:
                self.send_error(HTTPStatus.NOT_FOUND, "Replay draft not found")
                return
            markdown = Path(replay_path).read_text(encoding="utf-8", errors="replace")
            body = (
                '<section class="hero">'
                f"<h1>Replay Draft / {_escape(run_id)}</h1>"
                '<div class="nav"><a class="button" href="/">Back</a></div>'
                "</section>"
                f'<section class="report">{_markdown_to_html(markdown)}</section>'
            )
            self._send_bytes(
                _page(f"Replay {run_id}", body),
                "text/html; charset=utf-8",
                send_body=send_body,
            )
            return
        if artifact == "summary":
            summary_path = run.get("summary_path")
            self._serve_file(Path(str(summary_path)), send_body=send_body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown run artifact")

    def _serve_safe_file(
        self,
        root: Path,
        relative: str,
        *,
        send_body: bool,
    ) -> None:
        target = (root / relative).resolve()
        if not _is_relative_to(target, root) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        self._serve_file(target, send_body=send_body)

    def _serve_file(self, path: Path, *, send_body: bool) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix == ".md":
            content_type = "text/plain; charset=utf-8"
        elif path.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        elif path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        self._send_bytes(path.read_bytes(), content_type, send_body=send_body)

    def _send_bytes(
        self,
        payload: bytes,
        content_type: str,
        *,
        send_body: bool,
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(payload)


def make_dashboard_handler(
    *,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    evaluation_dir: str | Path = DEFAULT_EVALUATION_DIR,
) -> type[FeishuDashboardRequestHandler]:
    class ConfiguredFeishuDashboardRequestHandler(FeishuDashboardRequestHandler):
        pass

    ConfiguredFeishuDashboardRequestHandler.artifact_root = Path(artifact_root)
    ConfiguredFeishuDashboardRequestHandler.evaluation_dir = Path(evaluation_dir)
    return ConfiguredFeishuDashboardRequestHandler


def start_dashboard_server(
    *,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    evaluation_dir: str | Path = DEFAULT_EVALUATION_DIR,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> DashboardServerHandle:
    """Start the local dashboard server in a background thread."""

    handler = make_dashboard_handler(
        artifact_root=artifact_root,
        evaluation_dir=evaluation_dir,
    )
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError:
        if port == 0:
            raise
        server = ThreadingHTTPServer((host, 0), handler)
    actual_host, actual_port = server.server_address[:2]
    thread = threading.Thread(
        target=server.serve_forever,
        name="feishu-dashboard-server",
        daemon=True,
    )
    thread.start()
    return DashboardServerHandle(
        server=server,
        thread=thread,
        url=f"http://{actual_host}:{actual_port}/dashboard",
    )
