# Calendar Fixture Normalization And Runtime Logging

Date: 2026-05-06

## Module Analysis

Calendar currently has a partial Track ABCD slice: semantic page descriptors,
metadata-first state detection, router guidance, verifier branches, and report
recording. The slice still treats only `calendar_home` and
`calendar_event_modal` as first-class runtime states. New screenshots include
the time-slot quick-add path, a date picker popup, share/detail dialogs, and VC
settings, but the code path only validates the full create-event modal.

This can mix two different creation methods in logs:

- Full create dialog from the visible `创建日程` entry.
- Quick-add popup opened by clicking a calendar time slot.

The fixture directory also does not follow the IM rule yet: Calendar filenames
are Chinese, there is no `manifest.json` or `readme.md`, one PNG has no metadata,
and all metadata is still marked `draft/unreviewed`.

Runtime logging recently became safer but heavier. `record_observation()` calls
the full artifact sync on every screenshot, and the full sync rebuilds summary,
Markdown report, actions JSONL, runtime JSON, semantic trace, and replay draft.
The stdout tee also flushes after every write. That extra synchronous I/O runs
inside the AgentS3 step loop before prediction/action and can add latency or
change UI timing around screenshots.

## Boundaries

- Keep Calendar as agentic semantic guidance under `feishu_agent`.
- Do not add a deterministic Calendar workflow controller.
- Keep fixture metadata semantic-only: no coordinates, bbox, confidence, score,
  resolution, image dimensions, or ratio fields.
- Preserve live artifacts for failed, stopped, and successful runs, but avoid
  expensive Markdown/replay regeneration on every observation.

## Target Files

- `tests/fixtures/calendar/*`
- `gui_agents/feishu/pages/registry.py`
- `gui_agents/feishu/pages/calendar_quick_add_modal.py`
- `gui_agents/feishu/pages/calendar_date_picker.py`
- `gui_agents/feishu/detectors/calendar_state_detector.py`
- `gui_agents/feishu/tooling/tool_router.py`
- `gui_agents/feishu/verifiers/assertion_verifier.py`
- `gui_agents/feishu/contracts.py`
- `gui_agents/feishu/reports/s3_runtime_recorder.py`
- `gui_agents/s3/cli_app.py`
- Calendar and Track D tests under `tests/`

## Manual Plan

- Normalize Calendar fixture filenames to English snake_case and add
  `manifest.json` plus `readme.md`.
- Add missing metadata for the date picker screenshot and keep the quick-add
  fixture separate from the full create-event modal.
- Register semantic descriptors for `calendar_quick_add_modal` and
  `calendar_date_picker`.
- Teach detector/router/verifier to preserve quick-add vs full-create evidence
  in reports and semantic replay.
- Make observation-time artifact writes lightweight while keeping full sync on
  start, action, semantic step, and finalize.
- Change stdout tee flushing to line-oriented flushing.
- Verify with Calendar detector/router/verifier tests, Track D recorder tests,
  startup self-check, and CI parity if the focused suite passes.

## Risks And Rollback

Renaming fixtures can break stale references, so tests must use the new English
names and the manifest must list every PNG. If the logging change hides live
artifacts, rollback is limited to restoring full `_sync_artifacts()` from
`record_observation()` and always flushing the tee stream.
