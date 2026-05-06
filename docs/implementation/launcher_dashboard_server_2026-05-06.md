# Launcher Dashboard Server Integration

Date: 2026-05-06

## Module Role

Provide a launcher entry point for viewing Feishu evaluation artifacts through a
local read-only dashboard server.

The server converts existing run artifacts into browser-viewable pages and
serves them on localhost. It is a review/display layer only and does not call
AgentS3, WindowsFeishuACI, tool routing, locators, or any Feishu runtime
execution path.

## Boundary

In scope:

- Add a `Dashboard` button in `launcher.py`.
- Start a local read-only HTTP server on localhost.
- Regenerate existing aggregate evaluation outputs before serving.
- Serve the optimized evaluation dashboard.
- Serve converted per-run task reports from `artifacts/test_runs/*/report.md`.
- Serve replay drafts and JSON artifacts as review pages/files.

Out of scope:

- Live Feishu E2E execution.
- New regression runner.
- Editing or deleting artifacts.
- Any deterministic workflow or replay execution.
- External web dependencies or CDN assets.

## Key Interactions

```text
launcher Dashboard button
  -> start_dashboard_server()
  -> write_evaluation_report(artifacts/test_runs, artifacts/evaluation)
  -> localhost report portal
      -> /dashboard
      -> /runs/<run_id>/report
      -> /runs/<run_id>/replay
      -> /artifacts/evaluation/*
```

## Target Files

- `gui_agents/feishu/reports/dashboard_server.py`
- `launcher.py`
- `tests/feishu/reports/test_dashboard_server.py`
- `docs/implementation/launcher_dashboard_server_2026-05-06.md`

## Manual Plan

- target files: the files listed above.
- owner: Codex.
- depends on: existing `evaluation_aggregator.write_evaluation_report()` and
  per-run `summary.json` / `report.md` artifacts.
- outputs: launcher Dashboard button, localhost portal, converted task report
  pages.
- verification: focused dashboard server tests, launcher env tests, report
  tests, black, constraint check, startup gate.
- risks / rollback: if localhost serving causes issues, remove the launcher
  button and server module; existing artifact generation remains unchanged.

## Constraints

- Server binds to localhost only.
- Server is read-only: `GET` / `HEAD` only.
- Paths are resolved under known artifact roots and cannot traverse outside the
  project artifact directories.
- Markdown conversion is display-only and never executes code blocks.
- No screenshot-derived quantitative metadata is introduced.
- No workflow/planner/runtime changes.

## Verification

Executed:

- `python -m unittest tests.feishu.reports.test_dashboard_server tests.test_launcher_dashboard tests.test_launcher_env_config -v`
  - Passed: 16 tests OK.
- `python -m unittest tests.feishu.reports.test_dashboard_server tests.feishu.reports.test_evaluation_aggregator tests.feishu.reports.test_report_builder tests.feishu.reports.test_s3_runtime_recorder tests.test_launcher_dashboard tests.test_launcher_env_config -v`
  - Passed: 40 tests OK.
- `python -m black --check gui_agents/feishu/reports/dashboard_server.py launcher.py tests/feishu/reports/test_dashboard_server.py tests/test_launcher_dashboard.py`
  - Passed.
- `python scripts/check_constraints.py`
  - Passed: all constraints OK.
- `python -m unittest tests.test_agent_startup -v`
  - Passed: 183 tests OK.

Compatibility fix executed on 2026-05-06:

- Issue: `python launcher.py` failed in the `agent-S` environment because a
  dashboard HTML f-string contained a string literal with escaped newlines in
  the expression body.
- Fix: precompute the Markdown appendix HTML before the f-string and inject the
  prepared variable.
- Scope: display-only dashboard rendering; no runtime, workflow, replay, or
  Feishu execution path changed.
