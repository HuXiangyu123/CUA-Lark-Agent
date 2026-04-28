# Development Handoff

这份文档用于在新开 Codex/ChatGPT 上下文时快速恢复项目状态，避免重新阅读长聊天记录。新会话开始时，优先把“快速交接模板”复制给模型，然后按需要让模型阅读本文件和相关 README。

## 快速交接模板

可以直接复制下面这段作为新上下文的第一条消息：

```text
项目路径：H:\CUA-Lark-Agent
项目：CUA-Lark Agent，飞书/Lark 桌面 GUI 自动化 demo。目标是让 AI 像人一样通过截图理解界面，并操作鼠标键盘完成飞书任务，Windows 适配是当前重点。

当前分支：windows-refactor
远端：
- origin = https://github.com/HuXiangyu123/CUA-Lark-Agent.git，队友仓库，只读/无写权限
- myfork = https://github.com/xiaodeng-lp/CUA-Lark-Agent.git，我的 fork，可 push

当前 PR：
https://github.com/HuXiangyu123/CUA-Lark-Agent/pull/1
方向：xiaodeng-lp:windows-refactor -> HuXiangyu123:main

重要要求：
- 不要泄露或提交 .env、.env.backup*、API Key、traces、node_modules、.venv。
- CUA-Lark-TestCases/ 是本地测试数据，暂时不要提交；已写入 .git/info/exclude。
- 修改代码前先看 README_WINDOWS.md、DEVELOPMENT_HANDOFF.md，以及相关 agent/gui 文件。
- Windows GUI 路线已经测试过：截图、只观察、输入草稿不发送、清空草稿、发送消息、打开/搜索会话、打开日历、创建日程、飞书最小化恢复、多显示器截图。
- 单测命令：uv run python -m unittest discover -s tests
- 最近一次已通过：53 tests OK。

当前代码结构重点：
- agent/gui/capture.py：截图，Windows 多显示器用 ImageGrab.grab(all_screens=True)
- agent/gui/window.py：窗口查找、激活、最小化恢复、坐标转换
- agent/gui/controller.py：鼠标键盘动作，中文输入通过剪贴板粘贴
- agent/gui/langchain_agents.py：VLM/Responses API streaming 图片请求
- agent/gui/goals.py：目标分类和目标文本提取
- agent/gui/loop.py：观察、规划、执行、完成条件主循环
- README_WINDOWS.md：Windows 部署和测试说明

继续开发时请先运行：
git status --short --branch
uv run python -m unittest discover -s tests
```

## 当前仓库状态

本地仓库已初始化，并基于队友仓库 `origin/main` 创建了 Windows 适配分支：

```text
branch: windows-refactor
origin: https://github.com/HuXiangyu123/CUA-Lark-Agent.git
myfork: https://github.com/xiaodeng-lp/CUA-Lark-Agent.git
```

当前 PR：

```text
https://github.com/HuXiangyu123/CUA-Lark-Agent/pull/1
```

PR 状态截图中显示：

```text
Open
No conflicts with base branch
Changes can be cleanly merged
```

本地提交：

```text
00d3540 Add Windows GUI automation support
```

如果后续继续修改并希望更新 PR，提交到当前分支后 push：

```powershell
git add .
git commit -m "Your commit message"
git push
```

因为当前分支已经 tracking `myfork/windows-refactor`，普通 `git push` 会更新 fork 上的 PR 分支，不会直接改队友仓库 `main`。

## 不要提交的内容

这些必须保持本地：

```text
.env
.env.backup*
.venv/
node_modules/
lark-cli/node_modules/
traces/
__pycache__/
CUA-Lark-TestCases/
```

其中 `CUA-Lark-TestCases/` 是本地测试数据，暂时不要提交。它没有写进项目 `.gitignore`，而是写进了本地：

```text
.git/info/exclude
```

这样不会影响队友仓库。

提交前建议检查：

```powershell
git status --short --ignored
```

期望敏感和临时内容显示为 `!!` ignored，而不是 `??` untracked 或 staged。

## 已完成的 Windows 适配

当前 Windows 路线主要补齐了：

- Windows 下飞书/Lark 窗口查找、恢复、激活
- 飞书最小化时自动恢复并点击标题栏
- 多显示器截图，使用 `PIL.ImageGrab.grab(all_screens=True)`
- 中文输入通过 `pyperclip` 写入剪贴板后粘贴
- 单键动作例如 `Backspace` 使用 `pyautogui.press`
- GUI 图片请求使用 streaming Responses API
- 发送消息完成条件更严格，要求本轮确实输入并提交
- 清空草稿前先聚焦输入框左侧文本编辑区域，避免 `Ctrl+A` 选中整个页面
- 目标解析从 `loop.py` 拆到 `agent/gui/goals.py`
- 新增 Windows 部署文档 `README_WINDOWS.md`

## 主要功能测试

推荐按这个顺序测试：

```powershell
uv run python run.py capture --app Feishu --name feishu_window
uv run python run.py gui-run "观察当前飞书窗口，判断当前页面是什么，不要执行任何真实操作" --dry-run --json-output --progress
uv run python run.py gui-run "在当前飞书聊天输入框输入：CUA Windows 测试成功，但不要发送" --json-output --progress
uv run python run.py gui-run "清空当前飞书聊天输入框里的草稿内容，不要发送任何消息" --json-output --progress
uv run python run.py gui-run "在当前飞书聊天中发送消息：CUA Windows 端到端测试 001" --json-output --progress
uv run python run.py gui-run "打开飞书中的 bot功能测试 会话" --json-output --progress
uv run python run.py gui-run "在飞书中搜索 bot功能测试 并打开该会话" --json-output --progress
uv run python run.py gui-run "打开飞书日历模块" --json-output --progress
uv run python run.py gui-run "打开飞书日历，并在今天下午 6:30 创建一个日程，标题为：CUA 日历测试 0428" --json-output --progress
```

详细说明见 [README_WINDOWS.md](./README_WINDOWS.md)。

## 常用开发命令

检查分支和改动：

```powershell
git status --short --branch
git diff --stat
```

运行单元测试：

```powershell
uv run python -m unittest discover -s tests
```

编译检查：

```powershell
uv run python -m compileall -q agent tests
```

检查是否有明显乱码或疑似密钥：

```powershell
rg -n "鈥|鍙|鑱|椋|娑|�" -S --glob '!node_modules/**' --glob '!lark-cli/node_modules/**' --glob '!.venv/**' --glob '!traces/**' --glob '!.env' --glob '!.env.backup*' README.md README_WINDOWS.md DEVELOPMENT_HANDOFF.md agent tests .env.example
rg -n "sk-[A-Za-z0-9_-]{16,}|OPENAI_API_KEY\s*=\s*[^\s#]+|GUI_VLM_API_KEY\s*=\s*[^\s#]+|VLM_API_KEY\s*=\s*[^\s#]+|LARKSUITE_CLI_APP_SECRET\s*=\s*[^\s#]+" -S --glob '!node_modules/**' --glob '!lark-cli/node_modules/**' --glob '!.venv/**' --glob '!traces/**' --glob '!.env' --glob '!.env.backup*' .
```

## `.env` 说明

`.env` 里有真实 API Key，不能提交、不能贴到聊天里。新上下文只需要知道配置项结构，不需要知道真实值。

最少需要这些 GUI/VLM 配置：

```env
GUI_VLM_MODEL=gpt-5.5
GUI_VLM_API_BASE=https://your-provider.example/v1
GUI_VLM_API_KEY=your_api_key_here
GUI_TARGET_APP=Feishu
```

配置读取顺序：

```text
GUI_VLM_* -> VLM_* -> OPENAI_*
```

## 代码阅读顺序

新上下文接手时，建议按这个顺序读：

1. [README_WINDOWS.md](./README_WINDOWS.md)
2. [agent/gui/goals.py](./agent/gui/goals.py)
3. [agent/gui/loop.py](./agent/gui/loop.py)
4. [agent/gui/window.py](./agent/gui/window.py)
5. [agent/gui/capture.py](./agent/gui/capture.py)
6. [agent/gui/controller.py](./agent/gui/controller.py)
7. [agent/gui/langchain_agents.py](./agent/gui/langchain_agents.py)
8. [tests/test_gui_loop.py](./tests/test_gui_loop.py)
9. [tests/test_gui_window.py](./tests/test_gui_window.py)

`loop.py` 较大，除非要改完成条件或运行状态，不建议从它开始大范围重构。

## 已知注意事项

- PowerShell `Get-Content` 有时会把 UTF-8 中文显示成乱码，但文件本身可能是正常的。必要时用 Python 按 UTF-8 读取确认。
- Git 可能提示 `LF will be replaced by CRLF`，这是 Windows 换行警告，不等于代码错误。
- 发送消息的视觉校验可能受模型识别影响，所以当前逻辑允许“本轮输入并提交后输入框清空”作为发送成功证据。
- 清空草稿时重点是先聚焦输入框文本区域，否则 `Ctrl+A` 会选中整个飞书页面。
- 日历创建测试要用唯一标题，避免把旧日程误判成新结果。
- 如果要修改 PR，继续在 `windows-refactor` 分支提交并 `git push` 即可。
