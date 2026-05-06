# Dashboard Live Refresh And Pending Runs

Date: 2026-05-06

## Module Role

This pass improves the localhost review dashboard at
`http://127.0.0.1:8765/dashboard`.

The target is not runtime orchestration. The target is better visibility of
fresh run artifacts during manual review.

## Problem

Current `/dashboard` behavior has two review gaps:

- the page is generated from a point-in-time evaluation snapshot and then stays
  static in the browser until the user manually refreshes
- the dashboard only indexes run directories that already contain
  `summary.json`, so runs that have screenshots but have not finalized yet are
  invisible

This makes freshly executed tasks look missing even when artifacts are already
  appearing on disk.

## Boundary

In scope:

- add a dashboard JSON refresh endpoint
- add lightweight client polling for live dashboard refresh
- expose pending/incomplete run directories at the dashboard layer
- sort visible runs newest-first for review

Out of scope:

- changing AgentS3 runtime flow
- adding workflow execution
- changing report artifact contracts
- changing evaluation semantics

## Constraints

Must preserve:

- localhost read-only dashboard server
- `feishu_agent = AgentS3 + WindowsFeishuACI + Feishu semantic priors`
- existing `summary.json` / `report.md` artifact contract
- no deterministic workflow logic

## Key Interactions

```text
artifacts/test_runs/*
  -> summary.json present
      -> evaluation_aggregator summary
      -> /dashboard main run table
  -> screenshots only / partial artifacts
      -> dashboard_server pending run discovery
      -> dashboard pending banner

/dashboard page
  -> initial embedded evaluation snapshot
  -> periodic fetch /api/evaluation-summary
  -> auto refresh when snapshot changes
```

## Target Files

- `docs/implementation/dashboard_live_refresh_and_pending_runs_2026-05-06.md`
- `gui_agents/feishu/reports/evaluation_aggregator.py`
- `gui_agents/feishu/reports/dashboard_server.py`
- `tests/feishu/reports/test_dashboard_server.py`
- `tests/feishu/reports/test_evaluation_aggregator.py`

## Manual Plan

Target files:

- dashboard server, evaluation dashboard HTML generator, focused tests

Depends on:

- existing `write_evaluation_report()` pipeline
- existing `artifacts/test_runs/*/summary.json` contract
- existing launcher dashboard button and server startup flow

Outputs:

- dashboard JSON endpoint for current evaluation state
- auto-refreshing dashboard page
- pending run visibility for non-finalized artifact directories
- newest-first run ordering in dashboard review data

Verification:

- `python -m unittest tests.feishu.reports.test_dashboard_server tests.feishu.reports.test_evaluation_aggregator -v`
- `python scripts/check_constraints.py`
- `python -m unittest tests.test_agent_startup -v`

Risks / rollback:

- Risk: polling code breaks offline `evaluation_dashboard.html`.
  Mitigation: polling is best-effort and silently degrades when no API exists.
- Risk: pending detection shows noise from broken directories.
  Mitigation: only show immediate run directories with real artifact files and
  no `summary.json`.
- Rollback: remove polling script and API route; keep existing static dashboard.
