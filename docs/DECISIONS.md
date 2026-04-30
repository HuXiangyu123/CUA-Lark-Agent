# Decisions

This file records durable technical decisions and cautionary assumptions. Current code is the source of truth when older chat/docs conflict.

## D1. Use Real GUI Execution, Not Only API/CLI

Decision:

- Keep two routes: API route through `lark-cli`, and GUI route through screenshots + VLM + mouse/keyboard.
- Windows demo focus is the GUI route.

Why:

- Many desktop workflows cannot be represented cleanly through CLI/API.
- Product value includes helping users operate complex real UI, not only calling backend APIs.

Abandoned/limited:

- Do not treat `lark-cli` as a replacement for GUI task execution. It can assist setup/oracle later.

Do not assume:

- If an API exists, the demo should use it. The core CUA value is real UI operation.

## D2. Use Observe-Perceive-Plan-Act-Verify, One Action At A Time

Decision:

- The GUI loop executes a long-chain loop:
  `screenshot -> perception -> action decision -> bounds validation -> GUI action -> screenshot -> completion gate`.
- The model returns exactly one next action, not a full uncontrolled script.

Why:

- GUI state changes after every action.
- One-step planning allows traceability, retries, and safer irreversible actions.

Abandoned/limited:

- Do not ask the model to output a long action list and execute blindly.

Do not assume:

- Model "done" is enough. Code must verify with run state and visual evidence.

## D3. Completion Gates Live In Code, With Flow Modules For Heavy Domains

Decision:

- Completion gates remain code-owned through `GuiRunState`, `_refresh_done_gate`, `_done_gate_error`, and action/visual evidence.
- `agent/gui/loop.py` remains the orchestration layer.
- Chat-opening gate/update logic lives in `agent/gui/chat_flow.py`.
- Message-specific gate/update logic lives in `agent/gui/message_flow.py`.
- Calendar-specific gate/update logic lives in `agent/gui/calendar_flow.py`.

Why:

- Visual models may hallucinate completion.
- Old visible messages/events can be mistaken for newly completed work.
- User safety requires proving this run performed compose/submit/clear/save when relevant.

Examples:

- `send_message`: requires submit action plus visual confirmation, or typed target + submit + cleared composer.
- `compose_message`: requires exact target draft typed and visible without submit.
- `clear_composer`: requires composer empty and no submit.
- `create_calendar_event`: requires calendar visible, today/slot/editor/title/save/saved tile sequence.

Abandoned/limited:

- Model-only completion decisions.
- Treating historical visible content as current-run success.

Do not assume:

- A matching chat bubble or calendar tile visible before this run means success.
- A flow helper module means model output can bypass the run-state gate. The model still proposes one action at a time, while code validates and gates completion.

## D4. Separate Goal Parsing From Main Loop

Decision:

- Goal classification and extraction live in `agent/gui/goals.py`.
- `loop.py` imports underscore aliases for backwards-compatible tests/imports.

Why:

- `loop.py` was becoming too large and mixed.
- New task types should start with parsing/extraction before changing run gates.

Abandoned/limited:

- Continuing to pile natural-language parsing rules directly into `loop.py`.

Do not assume:

- All Chinese phrases are already covered. Add tests when expanding `goals.py`.

## D5. Windows Capture Uses Full Virtual Desktop And Cropping

Decision:

- On Windows, screenshots use Pillow/ImageGrab over all screens and crop to target window region.
- Current code includes high-DPI/multi-monitor handling.

Why:

- Feishu may be on a secondary monitor.
- Primary-screen-only capture caused wrong/black screenshots.

Abandoned/limited:

- `pyautogui.screenshot(region=...)` as the only Windows route.

Do not assume:

- Window coordinates and screenshot pixels are always 1:1 on Windows high-DPI displays.

## D6. Windows Window Activation Uses pygetwindow With Minimized Restore

Decision:

- `agent/gui/window.py` keeps the legacy class name `MacOSWindowManager`, but now supports non-macOS with pygetwindow.
- Minimized windows are restored; Windows may click the titlebar after restore.

Why:

- Feishu minimized or unfocused windows cannot be reliably captured/controlled.

Abandoned/limited:

- macOS-only AppleScript assumptions.

Do not assume:

- The class name means macOS-only behavior.
- `window.activate()` always throws only on failure; Windows can raise success-like errors.

## D7. Chinese Text Input Uses Clipboard Paste

Decision:

- `GuiController._type_text` uses clipboard paste when useful, especially for Chinese.

Why:

- Direct simulated keyboard input for Chinese is unreliable on Windows.

Abandoned/limited:

- Direct key-by-key typing for all text.

Do not assume:

- Clipboard side effects are harmless in all contexts; this is acceptable for current demo but may need restoration later.

## D8. VLM Calls Use Streaming Responses API

Decision:

- `agent/gui/langchain_agents.py` calls an OpenAI-compatible client directly and collects streaming Responses text.

Why:

- Some providers support vision through streaming Responses but return empty output for non-streaming image requests.

Abandoned/limited:

- Assuming `/chat/completions` or non-streaming image responses work for all providers.

Do not assume:

- The configured model supports image input just because text calls work.
- Provider behavior is stable; validate in new environments.

## D9. Test Data Is Local For Now

Decision:

- `CUA-Lark-TestCases/` holds 20 OSWorld-style local cases but is not currently committed.

Why:

- The user explicitly said not to submit that test folder yet.

Abandoned/limited:

- Do not include it in PR until explicitly requested.

Do not assume:

- Absence from Git means it is irrelevant; it is part of project context and future eval direction.

## D10. Future Direction: RAG + SOP, Not Endless Manual Enumeration

Decision/direction:

- Current successful flows are manually tested and partially rule-gated.
- Future scalable route should build Feishu docs/API/help-center RAG and workflow SOPs, then connect traces/test cases for self-improvement.

Why:

- Feishu/Coze-like products have high learning cost and changing UI.
- Text-only assistants can provide wrong instructions if they do not observe the actual UI.
- Manual enumeration does not scale to Docs, Workflow, approval, Base, and complex office processes.

Do not assume:

- More hard-coded goal kinds alone will solve general Feishu automation.

## D11. Token Cost Needs Architectural Optimization

Decision/direction:

- Current screenshot-every-step model calls are acceptable for demo, not for cost-efficient production.

Future options:

- State caching.
- Screenshot diff/change detection.
- Local/region cropping.
- Cheap model or rule pre-checks before expensive VLM calls.
- SOP/RAG context injection to reduce repeated reasoning.
- Strong model fallback only when uncertain/blocked.

Do not assume:

- More context always helps. It may increase cost and latency.

## D12. Current Code Over Historical Chat

Observed differences:

- Older handoff text said 53 tests; current code passes 64 tests.
- Older text said latest commit `9e85a04`; current latest is `0744188 Align Windows GUI automation with DPI awareness`.
- Root README has been updated from the old macOS-first wording to describe current Windows Feishu/Lark GUI support and link to `README_WINDOWS.md`.

Rule:

- Reconfirm actual state with `git log`, `git status`, and tests before continuing.

## D13. Windows Coordinate-Sensitive Paths Must Initialize DPI Awareness

Decision:

- On Windows, initialize DPI awareness before coordinate-sensitive operations such as window lookup, screenshot capture, and `pyautogui` execution.
- Current code centralizes this in `agent/gui/dpi.py` and calls it from `agent/gui/window.py`, `agent/gui/capture.py`, and `agent/gui/controller.py`.

Why:

- Mixed monitor scaling such as 120% + 150% can make window bounds, screenshot pixels, and mouse coordinates disagree.
- The planner may select the correct point in the screenshot while the real cursor lands on the wrong desktop location if those subsystems use different DPI modes.

Abandoned/limited:

- Do not assume high-DPI screenshot scaling alone is enough once actions move past the screenshot stage.
- Do not rely on whichever default DPI mode third-party libraries happen to inherit from the process.

Do not assume:

- Matching screenshot crops prove real click execution is correct.
- A fix in only `capture.py` solves the full screenshot -> plan -> translate -> execute chain on Windows laptops.

## D14. Composer Text Uses A Pending-Message State And Reset Flow

Decision:

- Send/compose runs carry a `pending_message_text` derived from the current target message.
- Before typing a pending message, if the composer is visibly non-empty or mismatched, the runner uses a deterministic reset flow: focus composer, select all, clear, then type the pending text.
- Message flow behavior lives in `agent/gui/message_flow.py`; `loop.py` delegates to it.

Why:

- Appending new text onto stale composer content can create mixed drafts and cause send flows to stall.
- The pending text state is also a foundation for future generated-reply flows where text is produced before it is typed and sent.

Do not assume:

- A non-empty composer is safe to reuse, even if part of it resembles the target.
- Clipboard paste alone is the message state. Clipboard paste is only the execution mechanism; the run state owns the pending text.

## D15. Keep `loop.py` As Orchestration, Not A Rule Dump

Decision:

- Keep extracting domain-heavy GUI flow logic out of `agent/gui/loop.py`.
- Current extracted modules are `agent/gui/chat_flow.py`, `agent/gui/message_flow.py`, and `agent/gui/calendar_flow.py`.
- Preserve backwards-compatible underscore wrappers in `loop.py` only where tests or existing imports still use them.

Why:

- `loop.py` was carrying the main runtime loop, visual-state updates, completion gates, and heuristics at the same time.
- Smaller flow modules make future changes easier to test without rewriting the observe/plan/act loop.

Do not assume:

- Refactoring should rewrite the loop wholesale. Prefer incremental extraction with tests after each step.

## D16. Send-Message Goals Separate Chat Target From Message Payload

Decision:

- For send-message goals, labeled message payloads such as `发送消息：...`, `发送信息：...`, or `send message: ...` take precedence over quoted chat/contact names.
- A send-message goal can carry both `target_label` and `pending_message_text`.
- Quoted text is still valid for simple goals such as `send message "hello-world" in current chat`.

Why:

- The timed task `搜索群聊“bot功能测试”并发送消息：CUA计时测试 ...` previously parsed `bot功能测试` as the message payload because it was the first quoted text.
- That caused the runner to type the group name and then repeatedly clear/retry because the actual requested payload was missing.

Do not assume:

- First quoted text is always the message. In multi-step goals it is often the target chat/contact.

## D17. Feishu Window Matching Must Handle Chinese Window Titles

Decision:

- `GUI_TARGET_APP=Feishu` must match both English `Feishu`/`Lark` titles and the Chinese desktop title `飞书`.
- The title matcher must not match unrelated windows such as Edge/PackyAPI.

Why:

- Feishu minimized restore code existed, but a matcher special case skipped the Chinese candidate after checking `Feishu/Lark`.
- A minimized real Feishu window titled `飞书` was present, while the run captured a browser instead.

Do not assume:

- PowerShell `Get-Content` display is authoritative for Chinese strings. Use Python UTF-8 reads for files and Unicode escapes in ad-hoc shell snippets when needed.

## D18. Send Confirmation Prefers Visual Status Icon, Waits Are Task-Specific

Decision:

- The perception schema includes `sent_message_status_visible`, `sent_message_status_kind`, and `sent_message_status_evidence`.
- A valid send/read status is a small green circular mark immediately to the right of the newest exact outgoing target message bubble.
- Empty green outline means sent but not seen; partially filled green circle means seen/read by at least one person. Both count as send-status evidence.
- Green avatars, online dots, buttons, checkboxes, sidebar badges, or icons not attached to the exact outgoing target message do not count.
- Synthetic waits use task-specific durations. Message exact-text and send-status checks use `100ms`; slower page/calendar stabilization can keep longer waits.

Why:

- Hard-coded waits made successful input/send flows slower and harder to reason about.
- Sending should be confirmed by screenshot evidence, not only by sleeping.

Do not assume:

- A wait action means one global sleep duration.
- A green UI element anywhere on the screen proves send success.
