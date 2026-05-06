# Feishu Unicode Clipboard Input Fix

Date: 2026-05-06

## Module Responsibility

Fix Feishu desktop text input for Chinese and other Unicode content when the
Windows default IME is active.

The Feishu agent should paste Unicode text into already focused or explicitly
targeted Feishu inputs. It should not rely on keyboard character typing for
Chinese text.

## Boundary

In scope:

- `agent.feishu_type(...)`
- `agent.feishu_type_message(...)`
- VC helper paths that delegate to `feishu_type(...)`
- Runtime-generated Python snippets for Feishu desktop input

Out of scope:

- Browser document typing helpers unless separately requested.
- New workflow executor or deterministic replay.
- Static coordinate metadata.
- Any change to product page descriptors.

## Current Failure

Observed live run:

- Calendar create-event dialog title input was focused.
- Model called `agent.feishu_type("项目同步")`.
- Next observation still saw an empty title field.

Likely cause:

- Current Feishu input snippets use `pyperclip.copy(...)` followed by
  `pyautogui.hotkey('ctrl', 'v')`.
- On Windows with the default IME active, the pyautogui hotkey path can fail to
  deliver paste reliably even though clipboard-based Unicode is the correct
  strategy.

Follow-up runtime failure after switching to Win32 paste:

- Generated helper functions inside the action snippet were valid.
- `gui_agents/s3/cli_app.py` executed the snippet with plain `exec(...)` inside
  a function scope.
- Nested helper calls inside the generated snippet could therefore fail with
  `NameError(...)` because defs/imports were not guaranteed to share one
  namespace.

## Manual Plan

Target files:

- `gui_agents/s3/cli_app.py`
- `gui_agents/s3/agents/grounding_feishu.py`
- `tests/feishu/reports/test_s3_cli_recorder_integration.py`
- `tests/feishu/tooling/test_feishu_runtime_prior_tools.py`
- `docs/implementation/feishu_unicode_clipboard_input_2026-05-06.md`

Depends on:

- Existing `WindowsFeishuACI` Feishu-specific agent actions.
- Existing clipboard-based semantic input design.

Outputs:

- A shared exec namespace helper in `cli_app.py` so generated helper defs remain
  visible inside the same action snippet.
- A shared generated-code paste block that:
  - writes Unicode text to clipboard,
  - verifies clipboard content when possible,
  - sends Ctrl+V through Win32 virtual key events,
  - optionally performs overwrite and Enter with Win32 key events,
  - writes trace lines for diagnosis.

Verification:

- Startup self-check.
- Focused Feishu runtime prior tool tests.
- Full CI parity check.

Risks and rollback:

- Risk: clipboard ownership briefly changes during the action.
  Mitigation: existing implementation already used clipboard; this only makes
  the paste delivery more reliable.
- Risk: a focused field is not actually focused.
  Mitigation: existing optional `element_description` click behavior remains.
- Rollback: restore previous `pyautogui.hotkey('ctrl', 'v')` paste snippets.

## Verification Evidence

Executed on 2026-05-06:

- `python -m unittest tests.test_agent_startup -v`
  - Result: passed, 202 tests.
- `python -m py_compile gui_agents\s3\agents\grounding_feishu.py`
  - Result: passed.
- Generated `agent.feishu_type("项目同步")` and
  `agent.feishu_type("项目同步", "添加主题", overwrite=True, enter=True)` code
  compile checks
  - Result: passed.
- `python -m unittest tests.feishu.tooling.test_feishu_runtime_prior_tools -v`
  - Result: passed, 9 tests.
- `python -m unittest tests.feishu.runtime.test_feishu_agentic_helpers tests.feishu.tooling.test_tool_router -v`
  - Result: passed, 18 tests.
- `python -m unittest tests.feishu.reports.test_s3_cli_recorder_integration -v`
  - Result: passed, 3 tests, including nested-helper exec scope coverage.
- `python scripts/run_ci_checks.py`
  - Result: passed.
