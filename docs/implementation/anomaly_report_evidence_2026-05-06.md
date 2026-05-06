# Feishu Anomaly Report Evidence Optimization

Date: 2026-05-06

## Module Responsibility

This optimization makes anomaly handling reviewable after a run completes. The
previous anomaly pass wrote semantic `anomaly_events` into runtime context; this
pass carries those events into summary, report, semantic trace, and replay draft
artifacts.

## Boundaries

- In scope:
  - sanitize anomaly events before report output;
  - expose anomaly counts, event list, and by-type totals in `summary.json`;
  - add a Markdown anomaly table to `report.md`;
  - annotate semantic trace steps with anomaly type and recovery hint;
  - create anomaly-only trace entries when no action step exists for the
    observed abnormal state;
  - show anomalies in `replay_draft.md`.
- Out of scope:
  - no automatic recovery action execution;
  - no deterministic modal dismissal or retry flow;
  - no coordinates, bbox, confidence, score, resolution, or image-size fields.

## Target Files

- `gui_agents/feishu/reports/report_builder.py`
- `tests/feishu/reports/test_report_builder.py`
- `docs/implementation/README.md`

## Manual Plan

- Target files: report builder, report builder tests, implementation index.
- Depends on: existing `runtime_context["anomaly_events"]` emitted by
  `S3RuntimeRecorder`.
- Outputs:
  - `summary["anomaly_events"]`;
  - `summary["anomaly_type_counts"]`;
  - `report.md` anomaly event table;
  - semantic trace `anomalies` and `recovery_hint` fields;
  - replay draft anomaly notes.
- Verification:
  - targeted report builder tests;
  - recorder tests to cover generated artifact bundle;
  - local CI parity through `python scripts/run_ci_checks.py`.
- Risks / rollback:
  - Report output might accidentally leak OCR or quantitative fields. Mitigate
    with sanitizer tests that assert forbidden terms stay absent.
  - Anomaly-only trace entries could be mistaken for executable replay steps.
    Mitigate with existing replay wording: the draft remains review-only and
    not executable.

