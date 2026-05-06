# Launcher Default Execution Mode Feishu Agent

Date: 2026-05-06

## Module Analysis

The launcher owns the desktop entry point for choosing model providers,
entering a task, and starting `gui_agents/s3/cli_app.py`. Runtime execution is
still performed by AgentS3; the launcher only passes `--execution_mode`.

Current execution modes remain:

- `classic_s3`: AgentS3 with the generic OSWorld grounding path.
- `feishu_agent`: AgentS3 with `WindowsFeishuACI` and Feishu semantic prior/tool
  guidance.

This change only switches the launcher default selection to `feishu_agent`.
It does not remove `classic_s3`, change product workflows, or introduce a new
runtime controller.

## Manual Plan

Target files:

- `launcher.py`
- `tests/test_launcher_env_config.py`
- `docs/implementation/README.md`

Depends on:

- Existing `EXECUTION_MODES` map.
- Existing `load_config()` behavior for merging `config.json`.

Outputs:

- New launcher configs default to `execution_mode = "feishu_agent"`.
- Missing or invalid saved execution mode falls back to `feishu_agent`.
- Launcher UI fallback labels use the configured default mode instead of a
  hardcoded `classic_s3`.

Verification:

- Focused launcher env/config tests.
- Startup self-check.
- Unified CI parity script.

Risks and rollback:

- Existing `config.json` files with an explicit `execution_mode` continue to be
  respected. If a user saved `classic_s3`, they can still choose it manually.
- Rollback is limited to resetting `DEFAULT_CONFIG["execution_mode"]` and the
  fallback labels to `classic_s3`.
