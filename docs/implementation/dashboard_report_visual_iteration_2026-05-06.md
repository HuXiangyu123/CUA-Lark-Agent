# Dashboard Report Visual Iteration

Date: 2026-05-06

## Module Role

This pass tightens the localhost evaluation review UI after visual inspection
of the live `/dashboard` and per-run `/runs/<run_id>/report` pages.

The work remains in the read-only reporting layer. It changes dashboard/report
presentation and review navigation only; it does not add runtime execution,
workflow replay, or any deterministic controller.

## Boundary

In scope:

- restyle per-run HTML report pages to the same Feishu blue/white language as
  `/dashboard`
- make dashboard run rows directly selectable, not only the small detail button
- shorten run IDs in the table to the final digest while preserving the full ID
  in tooltips/details
- shorten long task labels in task distribution and run table cells while
  preserving full text in tooltips/details
- verify the live localhost surface through page rendering/screenshot or DOM
  checks

Out of scope:

- changing markdown report contents
- executing replay drafts
- changing AgentS3 runtime decisions
- adding coordinate/bbox/confidence visual metadata

## Manual Plan

- target files:
  - `gui_agents/feishu/reports/dashboard_server.py`
  - `gui_agents/feishu/reports/evaluation_aggregator.py`
  - `tests/feishu/reports/test_dashboard_server.py`
  - `tests/feishu/reports/test_evaluation_aggregator.py`
- owner: Codex
- depends on:
  - existing dashboard server routes
  - existing static dashboard HTML generator
  - existing per-run HTML report builder
- outputs:
  - unified blue/white report detail pages
  - row-click dashboard selection
  - compact run/task labels
  - live page evidence for `http://127.0.0.1:8765/dashboard`
- verification:
  - focused report/dashboard tests
  - black check for touched files
  - local CI parity
  - live HTTP/render check on port 8765
- risks / rollback:
  - compact labels may hide useful IDs; full labels remain in title attributes
    and detail panel
  - report style changes apply to replay pages too because they share `_page`
  - rollback can revert presentation changes without touching runtime artifacts

