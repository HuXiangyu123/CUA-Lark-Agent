# Unified Evaluation Dashboard And Process Quality Metrics

Date: 2026-05-06

## Module Role

This pass unifies the localhost Feishu evaluation frontends into one dashboard
route and expands the review surface with process-quality metrics. The dashboard
remains a static/read-only artifact review UI for AgentS3 Feishu runs.

It does not introduce a deterministic runtime workflow, ordered replay executor,
or non-LLM control path. Report links, replay drafts, and evidence pages are
review artifacts only.

## Boundary

In scope:

- make `/dashboard` the single primary dashboard route
- redirect `/` to `/dashboard` instead of serving a separate portal frontend
- make the launcher open `/dashboard`
- preserve the current Chinese Feishu blue/white dashboard style
- add report, summary, replay, batch markdown, and Live E2E evidence links to
  the dashboard
- surface process-quality metrics:
  - step efficiency
  - partial credit
  - reflection count
  - redundant action rate
  - action distribution
  - locator stats
  - completion signal
  - exec errors
  - grouping by product, complexity, and priority

Out of scope:

- executing replay drafts
- changing AgentS3 planning or action semantics
- adding product-level workflow contracts
- persisting screenshot coordinates, bounds, confidence, image dimensions, or
  other quantitative visual metadata into semantic traces

## Key Interactions

```text
ReportBuilder
  -> summary.json process-quality fields

EvaluationAggregator
  -> evaluation_summary.json aggregate process metrics
  -> evaluation_dashboard.html unified Chinese review UI

dashboard_server
  -> / redirects to /dashboard
  -> /dashboard serves unified UI
  -> /runs/<run_id>/report keeps per-run HTML report viewer

launcher
  -> Dashboard button opens DashboardServerHandle.url
  -> handle.url points to /dashboard
```

## Manual Plan

- target files:
  - `gui_agents/feishu/reports/report_builder.py`
  - `gui_agents/feishu/reports/evaluation_aggregator.py`
  - `gui_agents/feishu/reports/dashboard_server.py`
  - `launcher.py`
  - `tests/feishu/reports/test_report_builder.py`
  - `tests/feishu/reports/test_evaluation_aggregator.py`
  - `tests/feishu/reports/test_dashboard_server.py`
  - `tests/test_launcher_dashboard.py`
- owner: Codex
- depends on:
  - existing report artifacts under `artifacts/test_runs/*`
  - existing static dashboard generator
  - existing local dashboard server
- outputs:
  - one primary `/dashboard` UI with dashboard metrics and report navigation
  - root-path compatibility redirect
  - richer aggregate process-quality facts
  - focused regression tests
- verification:
  - targeted report/dashboard/launcher tests
  - formatting check for touched Python files
  - `python scripts/run_ci_checks.py`
- risks / rollback:
  - process metrics may be missing on older summaries; render `-` and group as
    `unknown`
  - if route unification breaks existing browser bookmarks, root redirects to
    preserve compatibility
  - rollback can revert dashboard/server presentation changes without touching
    runtime execution

