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

## Manual Plan

Target files:

- `gui_agents/s3/agents/grounding_feishu.py`
- `tests/feishu/tooling/test_feishu_runtime_prior_tools.py`
- `docs/implementation/feishu_unicode_clipboard_input_2026-05-06.md`

Depends on:

- Existing `WindowsFeishuACI` Feishu-specific agent actions.
- Existing clipboard-based semantic input design.

Outputs:

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
- `python scripts/run_ci_checks.py`
  - Result: passed.
