# Runtime Incremental Artifacts And Abort Evidence

Date: 2026-05-06

## Module Analysis

The Feishu Agent runtime already records observations, actions, semantic steps,
and final assertions through `S3RuntimeRecorder`, but most structured artifacts
were previously written only from `finalize()`. That creates a bad failure mode:
if the process is terminated before `finalize()` completes, the run directory can
contain screenshots without `summary.json`, `report.md`, `actions.jsonl`, or a
replay draft.

This change keeps the current agentic runtime boundary:

- AgentS3 still decides every action.
- `WindowsFeishuACI` and Feishu semantic priors remain guidance/tool layers.
- The recorder only persists evidence; it does not control execution.
- The launcher only marks a known run as manually stopped when it terminates the
  child process.

## Manual Plan

Target files:

- `gui_agents/feishu/reports/s3_runtime_recorder.py`
- `gui_agents/s3/cli_app.py`
- `launcher.py`
- `tests/feishu/reports/test_s3_runtime_recorder.py`
- `tests/feishu/reports/test_s3_cli_recorder_integration.py`
- `tests/test_launcher_env_config.py`
- `docs/implementation/README.md`

Depends on:

- Existing `ArtifactManager` run directory helpers.
- Existing `ReportBuilder` summary/report/replay generation.
- Launcher stdout pipe and stop button lifecycle.

Outputs:

- Run directories are created at recorder start.
- `summary.json`, `report.md`, `actions.jsonl`, `replay_draft.md`,
  `runtime_state.json`, and `runtime_stdout.log` are available during a run and
  refreshed after observations/actions/semantic steps/final assertions.
- `record_action()` and its derived semantic-step update share one artifact sync,
  avoiding duplicate full-bundle writes per action.
- `FEISHU_RUNTIME_STARTED` is printed with run id and run directory so the
  launcher can associate a child process with its artifact directory.
- Finalize failures write `artifact_error.txt` instead of only printing a
  warning.
- Launcher stop marks known run artifacts as `aborted` and appends an abort note
  to `report.md` / `replay_draft.md`.

Verification:

- Focused recorder and launcher tests.
- Startup self-check.
- Unified CI parity script.

Risks and rollback:

- Incremental report writing adds small disk I/O after each recorded event, but
  it keeps artifacts reviewable after crashes or manual termination.
- Existing final artifact paths are preserved.
- Rollback is limited to removing the incremental sync and launcher abort marker
  helper.
