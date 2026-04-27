# CUA-Lark Agent

Feishu desktop GUI testing agent with two execution paths:

- `api`: call Feishu Open Platform abilities through `lark-cli`
- `gui`: use window screenshots, a general VLM, and real mouse/keyboard actions
- `auto`: route between API and GUI paths from the user instruction

The current implementation does not depend on a dedicated CUA model. The GUI path is built around a general multimodal model plus a macOS GUI executor.

## Supported Tasks

Current GUI coverage is centered on Feishu desktop:

- send a message in the current chat
- switch to a target group chat and verify the actual conversation is open
- open the Calendar module and verify the week view is active
- create a calendar event by selecting the date column and time row, typing the title, saving, and visually confirming the new event tile
- execute low-level GUI actions directly: click, double click, right click, drag, scroll, type, hotkey, wait

## Project Docs

- [background.md](./background.md)
- [prd.md](./prd.md)
- [spec.md](./spec.md)
- [SOP.md](./SOP.md)
- [tech_list.md](./tech_list.md)

## Architecture

### High-level modules

- `agent/`: Python agent runtime
- `agent/gui/`: screenshot capture, window management, LangChain agents, GUI loop, controller, trace
- `desktop/`: Electron shell so prompts can be run from a desktop UI instead of the terminal
- `lark-cli/`: Feishu CLI integration assets
- `scripts/`: helper scripts such as macOS permission preflight
- `tests/`: unit tests

### Execution paths

#### API path

1. User enters a request.
2. The router selects `api` or `auto -> api`.
3. The agent calls `lark-cli` commands.
4. Command output is returned to the user and stored in the conversation context.

#### GUI path

1. User enters a natural-language GUI goal.
2. The runner activates the Feishu window and reads the current window bounds.
3. The runner captures a window-level screenshot.
4. The perception route agent converts the screenshot into a structured UI state.
5. The action route agent decides exactly one next GUI action.
6. The runner validates coordinates against screenshot bounds.
7. The controller maps image coordinates back to screen coordinates and executes the action.
8. A new screenshot is captured and traced.
9. The state machine requires repeated matching observations before `submit` or `done`.

### LangChain GUI design

The GUI loop uses two LangChain agents defined in [agent/gui/langchain_agents.py](./agent/gui/langchain_agents.py):

- Perception route:
  - input: screenshot + recent history + run state summary
  - output: structured UI state such as `composer_text`, `composer_exact_match`, `sent_message_exact_match`, `blocked`, `confidence`
- Action route:
  - input: screenshot + recent history + run state summary
  - output: structured single-step decision with `status`, `stage`, `success_criteria`, and one `action`

The main loop lives in [agent/gui/loop.py](./agent/gui/loop.py) and records every step into `traces/`.

### Run-state and completion gates

The GUI route is not allowed to stop only because the screenshot "looks close enough". Each goal kind has an explicit completion gate:

- `send_message`
  - stale text already present in the composer is treated as baseline draft
  - submit is allowed only after the exact target text is visibly present and stable
  - completion requires a submit action plus post-send visual confirmation
- `open_chat`
  - selecting a chat row is not enough
  - the target conversation header or composer must visibly confirm the active chat
- `open_calendar`
  - completion requires the calendar view itself, not just a sidebar entry
  - the visible calendar state must be stable across repeated observations
- `create_calendar_event`
  - requires calendar visible
  - requires today's date or column visibly highlighted
  - requires a slot click in the current run
  - requires the visible editor time range to match the requested hint when one exists
  - requires the requested title to be visibly typed
  - requires a Save action in the current run
  - requires the saved event tile to be visible in the grid and stable
  - a matching event tile that was already visible before this run is treated as baseline only, not success

## Project Flow

### Recommended workflow

1. Start Feishu and keep the target chat window in the foreground.
2. Launch the Electron desktop shell with `npm run desktop`.
3. Fill in a prompt such as “当前打开的是飞书群聊 bot功能测试。请在当前聊天窗口发送消息 `hello-world`”.
4. The desktop shell focuses Feishu, syncs the current window size, hides itself, and starts the Python GUI loop.
5. The GUI loop runs observe -> perceive -> decide -> act until completion, blocked, or max steps.
6. Inspect the trace directory if the run fails or misbehaves.

### Desktop HUD behavior

During a desktop run the Electron shell can shrink to the top-right corner and show:

- live planner-derived todo steps
- current stage and status
- completion-gate reason when the task is not allowed to finish yet
- final trace path after the run exits

The todo list is driven by planner output plus run-state validation. It is not a hard-coded workflow.

### Debug workflow

1. Run `capture` to get a window screenshot.
2. Run `action` commands directly to validate low-level click/type/scroll/hotkey behavior.
3. Run `gui-run --dry-run` to verify planning and trace output without moving the mouse.
4. Run unit tests before changing loop logic.

## Setup

### Requirements

- macOS
- Python `3.12`
- `uv`
- Node.js + npm
- Feishu desktop client already installed and logged in

### Install dependencies

Python:

```bash
uv sync
```

Electron shell:

```bash
npm install
```

Common entry check:

```bash
uv run python run.py --help
```

## Configuration

Copy [.env.example](./.env.example) to `.env` and fill the values you actually use.

### 1. Lark CLI credentials

Used by the API route.

```env
LARKSUITE_CLI_APP_ID=
LARKSUITE_CLI_APP_SECRET=
LARKSUITE_CLI_BRAND=lark
```

### 2. Chat / API model

Used by the terminal chat path and API reasoning path.

```env
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4
```

### 3. GUI / VLM model

Used by the GUI route. This is the preferred configuration group for GUI runs.

```env
GUI_VLM_MODEL=
GUI_VLM_API_BASE=
GUI_VLM_API_KEY=
GUI_TARGET_APP=Feishu
GUI_MAX_STEPS=12
GUI_ACTION_PAUSE=0.5
GUI_STATE_DEBOUNCE=2
GUI_ENABLE_EMOJI_HEURISTIC=0
GUI_DRY_RUN=0
GUI_TRACE_DIR=traces
```

Compatibility aliases are still accepted:

```env
VLM_MODEL=
VLM_API_BASE=
VLM_API_KEY=
CUA_MODEL=
CUA_API_BASE=
CUA_API_KEY=
```

Resolution order for the GUI route is:

1. `GUI_VLM_*`
2. `VLM_*`
3. `OPENAI_*`

This means the GUI path can now run with only `GUI_VLM_API_KEY` configured; it does not require `OPENAI_API_KEY` if you are not using the API/chat path.

### 4. OCR

Reserved for future integration. Current code does not invoke OCR.

```env
OCR_ENABLED=0
OCR_PROVIDER=
OCR_MODEL=
OCR_API_BASE=
OCR_API_KEY=
```

## macOS Permissions

The app that launches the GUI workflow must have both permissions below:

- Screen Recording
- Accessibility

Typical launch targets:

- terminal workflow: `Terminal`, `iTerm`, `Warp`, `Cursor`, `VS Code`
- desktop workflow: the Electron app started by `npm run desktop`

If Screen Recording was just enabled, restart the launching app once.

Preflight check:

```bash
uv run python scripts/check_macos_gui.py
```

## Run

### Desktop app

Start:

```bash
npm run desktop
```

What it does:

1. lets you input a GUI prompt
2. checks permissions
3. focuses Feishu
4. syncs the current Feishu window width and height into the form
5. hides itself during execution so screenshots stay clean
6. restores itself and shows the trace path when done

### CLI REPL

Auto route:

```bash
uv run python run.py --mode auto
```

API route only:

```bash
uv run python run.py --mode api
```

GUI route REPL:

```bash
uv run python run.py --mode gui
```

### One-shot GUI run

Dry-run:

```bash
uv run python run.py gui-run "当前打开的是飞书群聊 bot功能测试。请在当前聊天窗口发送消息 hello-world" --dry-run --json-output
```

Real execution:

```bash
uv run python run.py gui-run "当前打开的是飞书群聊 bot功能测试。请在当前聊天窗口发送消息 hello-world" --json-output
```

Open a target chat:

```bash
uv run python run.py gui-run "打开群聊 \"bot功能测试\" 并确认当前会话真的已经打开" --json-output
```

Open Calendar:

```bash
uv run python run.py gui-run "打开calendar 日历并确认周视图已经打开" --json-output
```

Create a calendar event:

```bash
uv run python run.py gui-run "打开calendar 日历并在今天 6:30 PM 点击对应时间节点，创建标题为 \"demo-20260427-1830\" 的event并保存" --json-output
```

When repeating calendar tests, use a unique title so the visual verifier can distinguish a newly created event from an old visible tile.

### Manual low-level GUI actions

Capture only the Feishu window:

```bash
uv run python run.py capture --app Feishu --name feishu_home
```

Execute one action directly:

```bash
uv run python run.py action click --relative-to-app Feishu --x 180 --y 220
uv run python run.py action double_click --relative-to-app Feishu --x 500 --y 420
uv run python run.py action right_click --relative-to-app Feishu --x 500 --y 420
uv run python run.py action drag --relative-to-app Feishu --x 300 --y 300 --end-x 700 --end-y 300
uv run python run.py action scroll --relative-to-app Feishu --x 900 --y 700 --amount -600
uv run python run.py action type --text "Hello Feishu"
uv run python run.py action hotkey --keys command,k
uv run python run.py action wait --duration-ms 1500
```

## Trace and Debugging

Each GUI run writes artifacts under `traces/`, including:

- screenshots before and after steps
- planner output
- perception output
- step history
- final summary
- run-state snapshots, including workflow steps and completion-gate evidence

When a run fails, check:

1. whether the wrong app had focus
2. whether Screen Recording or Accessibility permissions were missing
3. whether the visible composer text was partial or unstable
4. whether the model returned coordinates outside the screenshot bounds
5. whether the calendar slot click opened the wrong time range
6. whether the event title was not visually extracted from the editor
7. whether a pre-existing visible event was mistaken for work completed in this run

## Validation

Unit tests:

```bash
uv run python -m unittest discover -s tests
```

Python syntax check:

```bash
uv run python -m py_compile agent/main.py agent/gui/*.py
```

Electron syntax check:

```bash
node --check desktop/main.js
node --check desktop/renderer/renderer.js
```

## Current Constraints

- macOS only
- tuned for Feishu desktop
- GUI completion still depends on visual confirmation and run-state evidence, not server-side truth
- OCR is not wired into the runtime yet
- the emoji heuristic fallback is disabled by default and only runs when `GUI_ENABLE_EMOJI_HEURISTIC=1`
- the calendar flow is currently tuned for Feishu week-view style layouts rather than every possible calendar surface
