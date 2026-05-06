# Semantic Trace Replay Draft

Date: 2026-05-06

## Status

Implementation plan for advanced feature 4 in
`docs/implementation/advanced_features_preliminary_plan.md`: semantic trace
recording and replay draft artifacts.

Implementation is in progress in the current workspace and remains scoped to
passive artifacts. It does not add replay execution.

## Module Responsibility

Record human-reviewable semantic facts from the active
`feishu_agent = AgentS3 + WindowsFeishuACI` route and emit passive artifacts
after a run completes.

This module does not choose actions, retry actions, or replay actions.

## Boundaries

In scope:

- Add semantic-only trace entries to `RuntimeContext.semantic_steps`.
- Write `semantic_trace.json` when semantic steps are present.
- Write `replay_draft.md` as a natural-language review draft.
- Keep existing `summary.json`, `report.md`, and `actions.jsonl` unchanged.

Out of scope:

- No deterministic replay executor.
- No fixed workflow or ordered product action sequence.
- No Worker loop rewiring in this change.
- No screenshot-derived coordinates, `relative_bounds`, `bbox`, confidence
  scores, image dimensions, or point values in the semantic trace contract.

## Image Input Gate

No new screenshots are required for this implementation scope.

The recorder can derive coarse semantic page/control facts from the current
runtime observation when that observation already contains OCR text or an
existing fixture path. It does not perform new manual image extraction and does
not store quantitative image data.

Stop and ask for human-provided images only if a future change requires one of
these:

- New product/page state not covered by existing detectors.
- Human validation of visible controls on a specific VC/Base/Calendar/Docs
  screenshot.
- Fixture creation for a UI state that cannot be represented by existing OCR
  text or fixture files.

If that happens, the required input should be:

- The screenshot file path or attached image.
- Product domain: `im`, `vc`, `docs`, `base`, or `calendar`.
- Expected semantic page type, for example `vc_home` or `vc_start_preview`.
- Human-visible controls/text that should be recognized.
- Expected assertion or review purpose.

Do not provide coordinates, bounding boxes, confidence scores, image size, or
pixel measurements.

## Key Interactions

`S3RuntimeRecorder` remains a passive observer. It owns the new
`record_semantic_step()` API and stores normalized entries in the current
runtime context.

`ReportBuilder` consumes `semantic_steps` at finalization time. It writes the
JSON trace and a Markdown replay draft only when the runtime context contains
semantic steps.

## Manual Plan

Target files:

- `gui_agents/feishu/reports/s3_runtime_recorder.py`
- `gui_agents/feishu/reports/report_builder.py`
- `tests/feishu/reports/test_s3_runtime_recorder.py`
- `tests/feishu/reports/test_report_builder.py`
- `docs/implementation/semantic_trace_replay_draft_2026-05-06.md`

Depends on:

- RuntimeContext optional field freeze for `semantic_steps`.
- Existing artifact manager JSON/text writers.
- Existing Track D finalization flow.

Outputs:

- `S3RuntimeRecorder.record_semantic_step(...)`
- `ReportBuilder.build_semantic_trace(runtime_context)`
- `ReportBuilder.build_replay_draft(runtime_context)`
- Optional artifact paths returned as `semantic_trace` and `replay_draft`

Verification:

- Unit test ReportBuilder semantic trace normalization and replay draft output.
- Unit test replay draft and trace reject forbidden quantitative keys.
- Unit test recorder persists semantic steps through `finalize()`.
- Unit test recorder derives semantic trace entries from existing observation
  facts without persisting raw executable code.
- Run targeted report tests plus repository constraint checks.

Risks and rollback:

- Risk: semantic step schema grows into another execution contract.
  Mitigation: no executable code field, no ordered replay API, artifact-only
  naming.
- Risk: raw state dictionaries leak quantitative keys.
  Mitigation: explicit allowlist normalization in builder and recorder tests.
- Rollback: remove the new recorder method and artifact writes; existing
  summary/report/actions artifacts remain unaffected.

## Verification Evidence

Executed on 2026-05-06:

- `python -m unittest tests.feishu.reports.test_report_builder tests.feishu.reports.test_s3_runtime_recorder -v`
  - Result: passed, 16 tests.
- `python -m unittest tests.test_agent_startup -v`
  - Result: passed, 181 tests.
- `python scripts/check_constraints.py`
  - Result: passed.
- `python scripts/run_ci_checks.py`
  - Result: passed.
