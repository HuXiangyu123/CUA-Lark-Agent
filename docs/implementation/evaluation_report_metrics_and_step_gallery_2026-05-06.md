# Evaluation Report Metrics And Step Gallery

Date: 2026-05-06

## Module Role

This pass expands the Feishu evaluation artifact layer so that it better
matches the project M4 reporting target and the teammate handoff sample
`handoff_feishu_eval_20260506_142139`.

The work stays inside Track D reporting and review surfaces:

- richer per-run structured metrics
- richer batch evaluation summary/report content
- improved localhost review frontend
- per-step screenshot display in HTML

It does not alter the active execution route. The runtime remains
`feishu_agent = AgentS3 + WindowsFeishuACI`, and no deterministic workflow
executor is introduced.

## Requirement Alignment

Primary source-of-truth references:

- `docs/项目需求.md`
- `docs/product/feishu_gui_agent_prd.md`
- `docs/spec/feishu_gui_agent_technical_spec.md`
- `docs/feishu_gui_agent_master_plan.md`

Relevant requirement signals extracted for this pass:

- M4 requires success rate, duration, and step statistics.
- Per-run artifacts must at least produce `summary.json` and `report.md`.
- Reports should include operation trace and key evaluation metrics.
- Review/demo surfaces should be visualizable and suitable for artifact audit.

The teammate handoff sample adds a useful presentation baseline:

- suite-level summary and markdown report
- case-level artifact manifest
- explicit screenshot chain per step

## Boundary

In scope:

- enrich `summary.json` with derived evaluation facts needed by offline review
- enrich `report.md` with clearer metric and artifact sections
- enrich aggregate evaluation JSON/Markdown/HTML
- improve fonts, layout, and visualization hierarchy for dashboard pages
- show per-step screenshots on the localhost HTML review path
- ignore the local handoff sample in `.gitignore`

Out of scope:

- changing AgentS3 prompting or execution semantics
- adding fixed `workflow.steps()` or ordered executor paths
- adding screenshot quantitative metadata
- trend comparison across historical batches
- cross-run orchestration changes

## Constraints

Must preserve:

- GUI-first runtime architecture
- display-only reporting behavior
- semantic-only screenshot/state extraction

Must not introduce:

- `bbox`, `relative_bounds`, `coordinates`, `confidence`, image dimensions, or
  other quantitative image fields into semantic trace or report payloads
- any report logic that drives runtime execution
- any fixed workflow replay behavior

## Key Interactions

```text
S3RuntimeRecorder
  -> runtime_context
  -> ReportBuilder
      -> summary.json
      -> report.md
      -> actions.jsonl
      -> semantic_trace.json
      -> replay_draft.md

artifacts/test_runs/*/summary.json
  -> EvaluationAggregator
      -> evaluation_summary.json
      -> evaluation_report.md
      -> evaluation_dashboard.html
      -> live_e2e_evidence.json
      -> live_e2e_evidence.md

dashboard_server
  -> reads run summary/report/replay/screenshot artifacts
  -> serves localhost review portal and per-run HTML view
```

## Target Files

- `gui_agents/feishu/reports/report_builder.py`
- `gui_agents/feishu/reports/evaluation_aggregator.py`
- `gui_agents/feishu/reports/dashboard_server.py`
- `.gitignore`
- `tests/feishu/reports/test_report_builder.py`
- `tests/feishu/reports/test_evaluation_aggregator.py`
- `tests/feishu/reports/test_dashboard_server.py`

## Implementation Plan

1. Extend per-run summary/report generation with requirement-aligned metrics and
   artifact manifest fields.
2. Extend aggregate evaluation summary/report/dashboard with stronger batch
   metrics and run-level artifact facts.
3. Upgrade localhost portal/run pages so reviewers can inspect step screenshots
   inline instead of only reading markdown paths.
4. Keep all HTML self-contained and read-only.
5. Add/update focused tests for metrics, HTML sections, and screenshot gallery.

## Verification Plan

Minimum verification after coding:

- `python -m unittest tests.feishu.reports.test_report_builder tests.feishu.reports.test_evaluation_aggregator tests.feishu.reports.test_dashboard_server -v`
- `python -m black --check gui_agents/feishu/reports/report_builder.py gui_agents/feishu/reports/evaluation_aggregator.py gui_agents/feishu/reports/dashboard_server.py tests/feishu/reports/test_report_builder.py tests/feishu/reports/test_evaluation_aggregator.py tests/feishu/reports/test_dashboard_server.py`
- `python scripts/check_constraints.py`
- `python -m unittest tests.test_agent_startup -v`

## Risks / Rollback

Risks:

- report payload growth if many screenshots are attached
- HTML becoming hard to scan if step galleries are not structured carefully
- leaking local absolute paths too aggressively into visible UI

Mitigations:

- keep screenshot rendering to artifact review pages, not semantic trace payloads
- normalize display sections around step cards and artifact manifest
- preserve machine-readable JSON while keeping HTML as a derived view

Rollback:

- revert report/dashboard presentation changes while preserving existing
  artifact writer contracts
- remove gallery rendering without changing runtime execution behavior

## Implementation Outcome

Completed:

- `summary.json` now includes richer derived metrics:
  - `result`
  - `planned_steps` / `observed_steps`
  - `step_pass_rate`
  - `assertion_pass_rate`
  - `screenshot_count`
  - `action_type_counts`
  - `completion_signal`
  - `step_artifacts`
  - `artifact_manifest`
- `report.md` now exposes richer metric sections, execution trace, step table,
  and step gallery references.
- aggregate evaluation output now includes:
  - artifact completeness metrics
  - action distribution totals
  - observed-step and assertion-pass averages
  - richer per-product rollups
  - richer run detail fields
- localhost dashboard pages now:
  - use aligned typography and stronger visual hierarchy
  - expose richer run metrics
  - render per-step screenshot cards in the run report HTML
  - serve run-local screenshot files safely through the dashboard server
- local teammate handoff sample paths are now ignored in `.gitignore`.

## Executed Verification

- `python -m unittest tests.feishu.reports.test_report_builder tests.feishu.reports.test_evaluation_aggregator tests.feishu.reports.test_dashboard_server -v`
  - Passed: 23 tests OK.
- `python -m unittest tests.feishu.reports.test_s3_runtime_recorder tests.test_launcher_dashboard -v`
  - Passed: 11 tests OK.
- `python scripts/check_constraints.py`
  - Passed: all constraints OK.
- `python -m black gui_agents/feishu/reports/dashboard_server.py tests/feishu/reports/test_evaluation_aggregator.py tests/feishu/reports/test_report_builder.py`
  - Executed to normalize formatting.
- `python -m black --check gui_agents/feishu/reports/report_builder.py gui_agents/feishu/reports/evaluation_aggregator.py gui_agents/feishu/reports/dashboard_server.py tests/feishu/reports/test_report_builder.py tests/feishu/reports/test_evaluation_aggregator.py tests/feishu/reports/test_dashboard_server.py`
  - Passed.
- `python -m unittest tests.test_agent_startup -v`
  - Passed twice during this implementation pass; latest run passed: 202 tests OK.

## Review Status

- `Claude Code` review not executed in this turn.
