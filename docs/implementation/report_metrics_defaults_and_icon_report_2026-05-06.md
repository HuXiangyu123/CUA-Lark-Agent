# Report Metrics Defaults And Icon Report

Date: 2026-05-06

## Module Analysis

The reporting slice is a review and evidence layer for the current
`feishu_agent = AgentS3 + WindowsFeishuACI` route. It must summarize what the
LLM-driven runtime already did; it must not become a deterministic controller or
ordered product workflow.

Relevant boundaries:

- `gui_agents/feishu/reports/report_builder.py` owns per-run metric derivation
  from runtime facts and testcase metadata.
- `gui_agents/feishu/reports/s3_runtime_recorder.py` owns runtime fact capture
  from the AgentS3 loop, including actions, observations, screenshots,
  semantic steps, anomaly events, and final assertions.
- `gui_agents/feishu/reports/evaluation_aggregator.py` owns cross-run
  aggregation and dashboard data defaults for historical summaries.
- `gui_agents/feishu/reports/dashboard_server.py` owns the local read-only HTML
  dashboard and per-run report pages.
- `gui_agents/s3/cli_app.py` is the integration point that can pass AgentS3
  reflection text into the recorder without changing agent decisions.

The current issue is that older and sparse runtime summaries can surface
`unknown` in priority, complexity, completion signal, product/status, locator
strategy, and report/dashboard fallback labels. Separately, the per-run report
page has the new Feishu blue-white shell but still lacks a clear process-quality
section and icon-led visual hierarchy.

## Manual Plan

Target files:

- `gui_agents/feishu/reports/report_builder.py`
- `gui_agents/feishu/reports/s3_runtime_recorder.py`
- `gui_agents/feishu/reports/evaluation_aggregator.py`
- `gui_agents/feishu/reports/dashboard_server.py`
- `gui_agents/s3/cli_app.py`
- `tests/feishu/reports/*`
- `docs/implementation/README.md`

Depends on:

- Existing runtime summaries and artifacts under `artifacts/test_runs`.
- Existing AgentS3 runtime loop; no new workflow executor is introduced.
- Existing report/dashboard server routing on `/dashboard` and
  `/runs/<run_id>/report`.

Outputs:

- Per-run summaries compute process-quality metrics with stable defaults:
  step efficiency, partial credit, reflection count, redundant action rate,
  action distribution, locator stats, completion signal, exec errors, priority,
  and complexity.
- Runtime recorder captures reflection text from the AgentS3 loop when present.
- Dashboard aggregation replaces display-facing `unknown` with useful defaults
  such as `general`, `medium`, `status_<status>`, or `not_recorded`.
- Per-run report page gains icon cards for result, evidence, process quality,
  locator quality, completion signal, and exec errors.

Verification:

- Run focused report tests.
- Run startup self-check.
- Run `python scripts/run_ci_checks.py`.
- Restart/verify the local dashboard server and check `/dashboard` plus a
  representative `/runs/<id>/report` page.

Risks and rollback:

- Historical reports cannot reconstruct missing runtime details; they should
  display graceful defaults while new runs record richer facts.
- Reflection capture depends on AgentS3 `info["reflection"]`; absent values
  remain zero-count, not `unknown`.
- Rollback is limited to the report/recorder/dashboard files listed above.
