# Project State

Last updated from local workspace on 2026-04-29.

## Current Goal

CUA-Lark Agent is being adapted from a macOS-first Feishu GUI agent into a Windows-runnable CUA demo: screenshot the real Feishu/Lark desktop window, use a multimodal model to perceive/plan, execute real mouse/keyboard actions, and verify task completion.

The product direction discussed by the team:

- Lower the learning cost of complex office software like Feishu.
- Go beyond text-only help that may not match the current UI.
- Handle GUI tasks that CLI/API cannot do.
- Later use Feishu docs/API guides/help docs + SOP + trace/test-case RAG so the agent can learn complex office workflows instead of requiring manual enumeration for every task.

## Current Progress

Implemented/available in the current code:

- Windows GUI route for Feishu/Lark desktop.
- Window activation, minimized-window restore, titlebar click fallback.
- Windows screenshot capture with multi-monitor/high-DPI support.
- Windows DPI-awareness initialization across window lookup, screenshot capture, and GUI execution to reduce mixed-scaling coordinate drift.
- Chinese text input via clipboard paste.
- Low-level manual actions: click, double click, right click, drag, scroll, type, hotkey, wait.
- GUI one-shot runner with perception/action model calls and trace output.
- Goal classification in `agent/gui/goals.py`.
- GUI loop refactor started: `agent/gui/loop.py` now keeps orchestration while chat-specific gates live in `agent/gui/chat_flow.py`, message-specific gates live in `agent/gui/message_flow.py`, and calendar-specific gates live in `agent/gui/calendar_flow.py`.
- Message send/compose flow now tracks a pending message text and deterministically focuses, selects, clears, then retypes when the composer already contains stale or mismatched text.
- Completion gates for:
  - `send_message`
  - `compose_message`
  - `clear_composer`
  - `send_emoji`
  - `open_chat`
  - `open_calendar`
  - `create_calendar_event`
- Windows deployment guide and compact handoff docs.
- PR exists: `https://github.com/HuXiangyu123/CUA-Lark-Agent/pull/1`.

Current git state observed:

```text
branch: windows-refactor
tracking: myfork/windows-refactor
origin: https://github.com/HuXiangyu123/CUA-Lark-Agent.git
myfork: https://github.com/xiaodeng-lp/CUA-Lark-Agent.git
latest local/remote commit: 9bd8640 Fix Windows high-DPI screenshot capture
```

Most recent local commit after this pass:

```text
0744188 Align Windows GUI automation with DPI awareness
```

## Current Run State

Verified locally in this handoff pass:

```powershell
uv run python -m py_compile run.py agent\gui\dpi.py agent\gui\capture.py agent\gui\window.py agent\gui\controller.py agent\gui\loop.py agent\gui\chat_flow.py agent\gui\message_flow.py agent\gui\calendar_flow.py
uv run python -m unittest discover -s tests
```

Result:

```text
Ran 64 tests
OK
```

Important difference from older handoff text: older docs/chat said 53 tests, and intermediate handoff text said 60 or 63 tests. Current code has 64 tests passing.

## Actual Entry Points And Commands

Actual Python entry file:

```text
run.py
```

Main command help:

```powershell
uv run python run.py --help
```

Install Python deps:

```powershell
uv sync
```

Install Electron deps if using desktop shell:

```powershell
npm install
```

Run Electron desktop shell:

```powershell
npm run desktop
```

Capture Feishu:

```powershell
uv run python run.py capture --app Feishu --name feishu_window
```

Dry-run observe:

```powershell
uv run python run.py gui-run "观察当前飞书窗口，判断当前页面是什么，不要执行任何真实操作" --dry-run --json-output --progress
```

Low-level dry-run action:

```powershell
uv run python run.py action click --relative-to-app Feishu --x 100 --y 100 --dry-run
```

GUI functional examples:

```powershell
uv run python run.py gui-run "在当前飞书聊天输入框输入：CUA Windows 测试成功，但不要发送" --json-output --progress
uv run python run.py gui-run "清空当前飞书聊天输入框里的草稿内容，不要发送任何消息" --json-output --progress
uv run python run.py gui-run "在当前飞书聊天中发送消息：CUA Windows 端到端测试 001" --json-output --progress
uv run python run.py gui-run "在飞书中搜索 bot功能测试 并打开该会话" --json-output --progress
uv run python run.py gui-run "打开飞书日历模块" --json-output --progress
```

## Interfaces And Runtime Checkpoints

External dependencies:

- Feishu or Lark desktop client installed and logged in.
- OpenAI-compatible multimodal model API that supports image input through Responses API.
- Python 3.12 via `uv`.
- Optional Node/Electron for desktop shell.
- `lark-cli` for API route, not required for GUI-only Windows tests.

Environment resolution:

GUI/VLM:

```text
GUI_VLM_API_BASE -> VLM_API_BASE -> CUA_API_BASE -> OPENAI_API_BASE
GUI_VLM_API_KEY  -> VLM_API_KEY  -> CUA_API_KEY  -> OPENAI_API_KEY
GUI_VLM_MODEL    -> VLM_MODEL    -> CUA_MODEL    -> OPENAI_MODEL
```

Important GUI env vars:

```text
GUI_TARGET_APP
GUI_MAX_STEPS
GUI_ACTION_PAUSE
GUI_STATE_DEBOUNCE
GUI_MIN_PERCEPTION_CONFIDENCE
GUI_VLM_TIMEOUT_SECONDS
GUI_CLEAR_MAX_DELETE_ATTEMPTS
GUI_ENABLE_EMOJI_HEURISTIC
GUI_DRY_RUN
GUI_TRACE_DIR
GUI_SCREENSHOT_MAX_DIMENSION
GUI_PROGRESS_STDERR
```

API/REPL env vars:

```text
OPENAI_API_BASE
OPENAI_API_KEY
OPENAI_MODEL
LARKSUITE_CLI_APP_ID
LARKSUITE_CLI_APP_SECRET
LARKSUITE_CLI_BRAND
```

Reconfirm in every new context:

- Current branch and uncommitted files: `git status --short --branch --ignored`.
- Current test count/result; do not rely on older "53 tests" text.
- On Windows mixed-scaling setups, verify whether the machine uses a single scale or mixed scales such as 120% + 150%.
- `.env` exists locally but must not be printed or committed.
- Whether Feishu is installed/logged in and target test chat exists.
- Whether the selected model/API endpoint really supports image input and streaming Responses API.
- Whether current PowerShell output is mojibake only in display or actual file corruption. Use Python UTF-8 reads to verify.
- Whether PR #1 has changed/merged since this handoff.

## Key Files

- `AGENTS.md`: stable agent rules.
- `docs/PROJECT_STATE.md`: this dynamic snapshot.
- `docs/DECISIONS.md`: technical decision record.
- `docs/TEST_LOG.md`: test and debugging record.
- `README_WINDOWS.md`: Windows deployment and test guide.
- `.env.example`: safe configuration template.
- `agent/main.py`: CLI parsing and entry dispatch.
- `agent/gui/loop.py`: main GUI loop orchestration.
- `agent/gui/chat_flow.py`: open-chat visual state and completion gate helpers.
- `agent/gui/message_flow.py`: message composer state, stale draft reset, pending text, and send/compose gates.
- `agent/gui/calendar_flow.py`: calendar visual state, event creation gates, time matching, and calendar action classification.
- `agent/gui/goals.py`: goal parsing.
- `agent/gui/langchain_agents.py`: VLM calls.
- `agent/gui/capture.py`: screenshots.
- `agent/gui/window.py`: window handling.
- `agent/gui/controller.py`: GUI execution.

## Known Issues And Risks

- Current successful workflows are still mostly tasks we explicitly tested/prompted. General Feishu workflow learning requires planned RAG/SOP work.
- Token cost is high because each GUI step can send screenshots to a large multimodal model.
- Visual verification can be imperfect; completion gates mitigate but do not remove all risk.
- Message composer behavior depends on reliably focusing the editable composer region before `Ctrl+A` / `Backspace`; layout changes may require retuning the focus heuristic.
- Feishu UI layout/version/language changes may break coordinate or semantic assumptions.
- Mixed-DPI Windows setups are now handled more deliberately, but still need repeated validation across more laptops, primary-monitor choices, and docking states.
- Calendar flow is tuned to currently observed week/day-like layouts and needs broader validation.
- Electron desktop path has Windows support but is less central than CLI `gui-run`; validate separately before demoing.
- Root `README.md` now points Windows users to `README_WINDOWS.md` and describes the GUI executor as cross-platform with current Windows Feishu/Lark support.

## Recommended Next Steps

1. Keep PR branch clean: commit these handoff docs and push to `myfork/windows-refactor`.
2. Before new feature work, choose one lane:
   - harden current demo stability, or
   - start RAG/SOP design, or
   - connect OSWorld-style cases to runner/eval.
3. For token optimization, prototype state caching/local screenshot crop strategy before broad prompt changes.
