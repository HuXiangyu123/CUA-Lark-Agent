# AGENTS.md

This file is the stable handoff/rules document for AI coding agents working on this repository. Keep it concise and factual. For dynamic status, read `docs/PROJECT_STATE.md`; for test history, read `docs/TEST_LOG.md`.

## Project Goal

CUA-Lark Agent is a Feishu/Lark desktop GUI automation demo. The goal is to let an AI agent observe the real desktop UI through screenshots, reason about the current task, operate mouse/keyboard like a user, and verify whether the task was actually completed.

The current priority is Windows support for Feishu desktop GUI workflows. The longer-term direction discussed by the team is to reduce manual workflow enumeration by combining:

- Feishu docs/API/help-center RAG
- reusable Feishu workflow SOPs
- OSWorld-style task cases
- success/failure trace learning

## Key Directories And Modules

- `run.py`: actual Python entry point. It delegates to `agent.main:main`.
- `agent/main.py`: CLI parser, `.env` loading, REPL/API/GUI mode dispatch.
- `agent/gui/loop.py`: main observe -> perceive -> plan -> act -> verify orchestration. High risk; avoid broad edits without tests.
- `agent/gui/message_flow.py`: message composer flow helpers, including pending-message text, stale draft reset, send/compose gates, and message visual/execution state updates.
- `agent/gui/calendar_flow.py`: calendar flow helpers, including calendar visual state updates, event creation gates, time matching, and calendar action classification.
- `agent/gui/goals.py`: goal classification and target extraction, e.g. send message, clear composer, open chat/calendar, create event.
- `agent/gui/langchain_agents.py`: OpenAI-compatible multimodal Responses API calls for perception/action routing.
- `agent/gui/capture.py`: screenshot capture, including Windows multi-monitor/high-DPI handling.
- `agent/gui/window.py`: target app activation, minimized-window restore, bounds lookup, coordinate translation.
- `agent/gui/controller.py`: real GUI execution through pyautogui; Chinese typing uses clipboard paste.
- `agent/gui/prompts.py`: perception/action prompt contract.
- `agent/gui/schema.py`: action/decision schema validation.
- `agent/gui/trace.py`: per-run trace artifacts and summaries.
- `desktop/`: Electron shell. `npm run desktop` uses `desktop/launch-electron.cjs`.
- `tests/`: unit tests. Run before committing.
- `README_WINDOWS.md`: Windows deployment/testing guide.
- `DEVELOPMENT_HANDOFF.md`: older long-context handoff file; this AGENTS/docs set is the newer compact source of truth.
- `CUA-Lark-TestCases/`: local OSWorld-style test dataset. It is intentionally ignored locally and is not currently submitted.

## Stable Rules And Boundaries

- Do not commit or print secrets from `.env`, `.env.backup*`, API keys, provider URLs with credentials, or local tokens.
- Do not commit generated/local directories: `.venv/`, `node_modules/`, `lark-cli/node_modules/`, `traces/`, `__pycache__/`.
- `CUA-Lark-TestCases/` is local test data for now. It is excluded through `.git/info/exclude`; do not add it unless explicitly asked.
- Prefer targeted changes. `agent/gui/loop.py` is large and stateful; read relevant tests before editing completion gates.
- For GUI features, preserve the rule: the model proposes one action at a time, but code validates bounds, records run state, and gates completion.
- Do not trust old chat assumptions over current code. If they conflict, current code wins.
- When touching Chinese strings, verify with Python UTF-8 reads, not only PowerShell `Get-Content`, because PowerShell may display mojibake even when the file is correct.

## Main Runtime Chain

GUI one-shot path:

```text
run.py -> agent.main.main()
  -> gui-run subcommand
  -> init_gui_client()
  -> GuiRunner.run(goal)
  -> Windows DPI awareness init for coordinate-sensitive paths
  -> MacOSWindowManager.activate/window_info
  -> ScreenCapture.capture
  -> LangChainGuiAgentSuite.perceive / decide
  -> translate_action_from_image_to_screen
  -> GuiController.execute
  -> TraceRecorder writes screenshots/json/summary
  -> _refresh_done_gate decides completion
```

Interactive/API path:

```text
run.py -> agent.main.main()
  -> REPL with mode auto/api/gui
  -> API path calls lark-cli through agent.executor
  -> GUI path uses GuiRunner
```

## Low-Token Working Style

In a new context, do not reread the whole repo. Start with:

```powershell
git status --short --branch
Get-Content AGENTS.md
Get-Content docs\PROJECT_STATE.md
Get-Content docs\DECISIONS.md
Get-Content docs\TEST_LOG.md
```

Then read only the files relevant to the task:

- Runtime/CLI issue: `agent/main.py`, `run.py`.
- Goal parsing issue: `agent/gui/goals.py`, related tests in `tests/test_gui_loop.py`.
- Completion gate issue: `agent/gui/loop.py`, `agent/gui/message_flow.py`, `agent/gui/calendar_flow.py`, `tests/test_gui_loop.py`.
- Screenshot/window issue: `agent/gui/capture.py`, `agent/gui/window.py`, `tests/test_gui_window.py`.
- VLM/API issue: `agent/gui/langchain_agents.py`, `.env.example`, `README_WINDOWS.md`.

Default verification:

```powershell
uv run python -m unittest discover -s tests
```

Use focused py_compile when changing entrypoints or syntax-sensitive files:

```powershell
uv run python -m py_compile run.py agent\gui\loop.py agent\gui\message_flow.py agent\gui\calendar_flow.py agent\gui\goals.py
```

## Suggested New-Context Start

Tell the next assistant:

```text
Please read AGENTS.md, docs/PROJECT_STATE.md, docs/DECISIONS.md, and docs/TEST_LOG.md first. Do not continue implementation until you confirm current git status and the actual runtime commands from the docs. Then help with the specific next task.
```
