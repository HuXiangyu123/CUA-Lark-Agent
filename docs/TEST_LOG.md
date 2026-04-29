# Test Log

This is a compact test/debug record. Do not paste raw logs here; keep only information needed for future reproduction and debugging.

Last local verification during this handoff:

```powershell
uv run python -m py_compile run.py agent\gui\dpi.py agent\gui\capture.py agent\gui\window.py agent\gui\controller.py agent\gui\loop.py agent\gui\chat_flow.py agent\gui\message_flow.py agent\gui\calendar_flow.py
uv run python -m unittest discover -s tests
```

Result:

```text
Ran 64 tests
OK
```

## Verified Key Chains

### 1. CLI Entry And Unit Tests

How tested:

```powershell
uv run python run.py --help
uv run python -m unittest discover -s tests
```

Result:

- Success locally.
- Current unit test count: 64.

Notes:

- Older chat/docs referenced 53 tests, and older handoff text referenced 60 or 63 tests. Current code has advanced to 64.

### 2. Feishu Window Capture

How tested:

```powershell
uv run python run.py capture --app Feishu --name feishu_window
Start-Process .\traces\feishu_window.png
```

Result:

- Success after Windows capture/window fixes.

Key errors seen:

- Screenshot did not show Feishu; sometimes showed VS Code/PowerShell or wrong screen.
- Black/wrong capture risk on secondary monitor/high-DPI setups.

Suspected causes:

- Feishu not active or minimized.
- Multi-monitor virtual desktop not handled.
- Windows DPI/window coordinates did not map directly to screenshot pixels.

Fix record:

- Window restore/activate/titlebar click in `agent/gui/window.py`.
- Windows desktop capture/cropping and later high-DPI fix in `agent/gui/capture.py`.

Residual risks:

- Needs revalidation on new monitor scaling/DPI setups.
- Feishu title/language changes can affect window matching.

### 3. Observe-Only GUI Run

How tested:

```powershell
uv run python run.py gui-run "观察当前飞书窗口，判断当前页面是什么，不要执行任何真实操作" --dry-run --json-output --progress
```

Result:

- Success in the Windows demo environment.

Purpose:

- Validates screenshot + VLM perception path without real mouse/keyboard actions.

Residual risks:

- Depends on image-capable provider and streaming Responses API behavior.

### 4. Low-Level Mouse/Keyboard Action

How tested:

```powershell
uv run python run.py action click --relative-to-app Feishu --x 100 --y 100 --dry-run
uv run python run.py action type --text "你好，CUA 测试" --dry-run
```

Result:

- Dry-run path works.
- Real mouse movement/click was later observed working.

Key errors seen:

- Early concern that mouse did not move; later user confirmed it moved.

Fix/notes:

- For real execution, remove `--dry-run` only in safe UI state.

Residual risks:

- Real click coordinates depend on current window bounds/DPI.

### 4A. Windows Mixed-DPI Coordinate Consistency

How tested:

```powershell
Set-Location H:\CUA-Lark-Agent
uv run python run.py capture --app Feishu --name dpi_mixed_check
Start-Process .\traces\dpi_mixed_check.png
uv run python run.py gui-run "观察当前飞书窗口，判断当前页面是什么，不要执行任何真实操作" --dry-run --json-output --progress
uv run python run.py action click --relative-to-app Feishu --x 100 --y 100 --dry-run
uv run python run.py action click --relative-to-app Feishu --x 100 --y 100
uv run python -m unittest tests.test_gui_dpi
uv run python -m unittest discover -s tests
```

Environment:

- Windows laptop/desktop mixed scaling reproduction: one monitor at 120%, one monitor at 150%.

Result:

- Dry-run action path and unit tests succeeded.
- Real click path was exercised manually in the mixed-scaling environment before pushing the code update.
- Code was updated and pushed in commit `0744188` (`Align Windows GUI automation with DPI awareness`).

Key errors seen:

- On some Windows laptops, the model could choose the correct point in the screenshot but the actual mouse click still landed at the wrong desktop location.
- This was most suspicious when monitor scaling differed across displays.
- A separate manual typo was also observed once: `--y 100v` caused argparse to reject the command. That was a command input error, not a coordinate bug.

Suspected causes:

- `pygetwindow`, Pillow `ImageGrab`, Win32 screen metrics, and `pyautogui` were not guaranteed to share the same DPI awareness mode.
- Under Windows scaling, screenshot pixels, window bounds, and actual mouse coordinates could silently refer to different coordinate spaces.

Fix record:

- Added `agent/gui/dpi.py` with `ensure_windows_dpi_awareness()`.
- On Windows, the process now attempts `PER_MONITOR_AWARE_V2`, then `PER_MONITOR_AWARE`, then older DPI-awareness fallbacks.
- Wired this DPI-awareness initialization into:
  - `agent/gui/capture.py`
  - `agent/gui/window.py`
  - `agent/gui/controller.py`
- Added regression tests in `tests/test_gui_dpi.py`.

Residual risks:

- Mixed-DPI behavior still needs repeated validation on more than one physical laptop and with different primary-monitor selections.
- If a third-party library caches screen metrics before DPI awareness is set in a future refactor, coordinate drift could reappear.
- The current fix targets the most likely Windows root cause, but real Feishu end-to-end flows should still be rechecked after monitor layout changes, docking, or RDP.

### 5. Compose Draft Without Sending

How tested:

```powershell
uv run python run.py gui-run "在当前飞书聊天输入框输入：CUA Windows 测试成功，但不要发送" --json-output --progress
```

Result:

- Success in manual testing.

Key implementation:

- Goal kind `compose_message`.
- Completion gate requires this run typed exact target and visually verified composer text, with no submit action.

Residual risks:

- Visual model must correctly read composer text.
- If Feishu UI changes composer layout, focus/click may need retuning.

### 6. Clear Draft

How tested:

```powershell
uv run python run.py gui-run "清空当前飞书聊天输入框里的草稿内容，不要发送任何消息" --json-output --progress
```

Result:

- Eventually successful.

Key errors seen:

- `Ctrl+A` selected the whole Feishu page instead of composer text.
- Earlier drag/select/delete path produced too many steps and unreliable focus.

Suspected causes:

- Composer text area not focused when select-all ran.

Fix record:

- Added clear-composer goal kind and heuristic flow.
- Click composer text area before select-all/delete.
- Use `Ctrl+A` + `Backspace`.
- Gate success on composer empty and no submit action.
- `GUI_CLEAR_MAX_DELETE_ATTEMPTS` limits retries.

Residual risks:

- Composer text area location/layout can vary.
- Visual read of composer emptiness can fail; trace inspection needed.

### 7. Send Message

How tested:

```powershell
uv run python run.py gui-run "在当前飞书聊天中发送消息：CUA Windows 端到端测试 001" --json-output --progress
```

Result:

- Success in manual testing.

Key errors seen:

- Message was sent, but program could not judge success and restarted/retried.
- Send target sometimes included both input-box and send-button semantics.
- Old visible matching messages could look like success.

Suspected causes:

- Visual extraction of latest message imperfect.
- Completion relied too much on model done/visible history.

Fix record:

- Submit action detection prioritizes explicit send controls.
- Send gate requires this run executed submit.
- Success can be confirmed by target visible after submit, or by this run typed target + submitted + composer cleared.
- Baseline guards reject old visible content before current-run submit.
- Message flow was later refactored into `agent/gui/message_flow.py`.
- Send/compose runs now track `pending_message_text`; when the composer is non-empty or mismatched before typing, the runner focuses the composer, selects all, clears stale text, then types the pending message.

Residual risks:

- If composer does not clear after send and latest message is not recognized, success may remain blocked.
- Need more cases across Feishu language/theme/layout variants.

### 7A. GUI Loop Refactor And Composer Reset Regression

How tested:

```powershell
uv run python -m py_compile agent\gui\loop.py agent\gui\chat_flow.py agent\gui\message_flow.py agent\gui\calendar_flow.py tests\test_gui_loop.py
uv run python -m unittest tests.test_gui_loop
uv run python -m unittest discover -s tests
```

Result:

- Success locally.
- Current unit test count: 64.

Fix/refactor record:

- Added `agent/gui/message_flow.py` for message compose/send visual state, execution state, pending text reset, submit gate, and done gate helpers.
- Added `agent/gui/calendar_flow.py` for calendar visual state, calendar done gates, action classification, and time matching helpers.
- Added `agent/gui/chat_flow.py` for open-chat visual state and completion gate helpers.
- Kept `agent/gui/loop.py` as the orchestration layer with compatibility wrappers where tests/imports still use underscored helpers.
- Added regression coverage that a non-empty composer is focused, selected, cleared, and only then receives the pending message text.

Residual risks:

- Some compatibility wrappers remain in `loop.py`; future cleanup should remove them only after imports/tests are moved to the flow modules.
- Real Feishu composer focus behavior still needs GUI validation after layout, language, or theme changes.

### 8. Open/Search Target Chat

How tested:

```powershell
uv run python run.py gui-run "打开飞书中的 bot功能测试 会话" --json-output --progress
uv run python run.py gui-run "在飞书中搜索 bot功能测试 并打开该会话" --json-output --progress
```

Result:

- Manual testing reported success for search/open conversation.

Key implementation:

- Goal kind `open_chat`.
- Gate requires target chat visibly open, not just row clicked.

Residual risks:

- Target chat title extraction depends on goal phrasing.
- Search result layouts may vary.

### 9. Calendar Open And Event Creation

How tested:

```powershell
uv run python run.py gui-run "打开飞书日历模块" --json-output --progress
uv run python run.py gui-run "打开飞书日历，并在今天下午 6:30 创建一个日程，标题为：CUA 日历测试 0428" --json-output --progress
```

Result:

- Manual testing reported calendar module and event creation completed.

Key implementation:

- Goal kinds `open_calendar` and `create_calendar_event`.
- Event creation gate requires calendar visible, today highlighted, slot click, editor visible, title typed, Save action, saved event tile visible, and stable visual state.
- Existing matching event before slot/save is baseline only.

Residual risks:

- Time-slot detection is layout-sensitive.
- Time hint parsing may need more Chinese/English variants.
- Reuse unique event titles to avoid baseline confusion.

### 10. Minimized Feishu Restore

How tested:

- User requested support for minimized Feishu.
- Subsequent flows used window restore/activate behavior.

Result:

- Current code supports restore/activate path in `agent/gui/window.py`.

Key errors seen:

- If Feishu was minimized, screenshots/actions could fail or target wrong window.

Fix record:

- Detect minimized window, restore it, activate it, and click titlebar on Windows.

Residual risks:

- Windows focus stealing restrictions may still interfere on some machines.

### 11. VLM Image Request

How tested:

- User confirmed provider/API can receive images.
- Program path was inspected and updated.

Result:

- Current `agent/gui/langchain_agents.py` uses streaming Responses API and tests pass.

Key errors seen:

- Initial assumption that model/API could not accept images was wrong.
- Non-streaming/other route could return empty output.

Fix record:

- Use OpenAI-compatible streaming Responses API and collect text deltas.

Residual risks:

- Provider-specific Responses API compatibility must be validated in new environments.
- Model name in `.env` must truly support image input.

### 12. GitHub/PR Flow

How tested:

```powershell
git push -u origin windows-refactor
```

Result:

- Failed with 403 because current GitHub user did not have write permission to teammate repo.

Fix record:

- Added `myfork` remote: `https://github.com/xiaodeng-lp/CUA-Lark-Agent.git`.
- Pushed `windows-refactor` to fork.
- Created PR to teammate repo: `https://github.com/HuXiangyu123/CUA-Lark-Agent/pull/1`.

Residual risks:

- Reconfirm PR state before assuming it is open/unmerged.

## Known Historical Bugs And Fixes

| Issue | Condition | Suspected Cause | Fix/Current State | Residual Risk |
|---|---|---|---|---|
| Screenshot not Feishu | Feishu unfocused/minimized/secondary monitor | Window activation/capture mismatch | Window restore/activate + all-screen capture/crop | DPI/layout variants |
| Image input failure | VLM call with screenshots | Program call path, not necessarily model support | Streaming Responses API | Provider differences |
| Clear draft failed | `Ctrl+A` selected whole Feishu page | Composer not focused | Click text area then Ctrl+A/Backspace | Composer layout changes |
| Send success not detected | Sent message but run retried | Visual latest-message extraction imperfect | Done gate allows typed+submit+composer-cleared evidence | Some send states may still block |
| Old message/event counted as success | Existing visible content matched target | No baseline distinction | Baseline guards and current-run action requirements | Need more regression tests |
| Direct push denied | Pushing to teammate repo | No write permission | Push to fork and PR | PR must be reviewed/merged |

## Pending / To Verify

- Real end-to-end GUI flows after latest high-DPI capture fix on the same demo machine.
- Electron desktop shell on Windows after `desktop/launch-electron.cjs` changes.
- OSWorld-style `CUA-Lark-TestCases/` integration into automated eval; currently local and ignored.
- Token optimization strategy: cache/diff/crop/model-tiering/RAG/SOP.
- RAG over Feishu docs/API/help-center is planned, not implemented.
