# CUA-Lark Agent Windows 部署与测试指南

这份文档记录当前项目在 Windows 上的部署、配置、运行和测试方法。原项目偏 macOS 环境，本版本已补齐 Windows 下的飞书/Lark 桌面 GUI 自动化能力：通过窗口截图、多模态模型理解界面，再用真实鼠标和键盘完成操作。

如果要新开 Codex/ChatGPT 上下文继续开发，请先看 [DEVELOPMENT_HANDOFF.md](./DEVELOPMENT_HANDOFF.md)，里面有可直接复制的新上下文交接模板。

当前 Windows GUI 路线已经围绕以下场景做过测试：

- 截取并理解当前飞书窗口
- 飞书窗口最小化后自动恢复、激活并截图
- 在当前聊天输入框输入草稿但不发送
- 清空当前聊天输入框草稿
- 发送消息并校验发送后的状态
- 搜索并打开指定会话
- 切换飞书模块，例如消息和日历
- 打开日历模块
- 创建日程并校验日程是否出现在日历中
- Windows 多显示器截图

## 1. 环境要求

建议使用：

- Windows 10 或 Windows 11
- 已安装并登录的飞书或 Lark 桌面客户端
- Python `3.12`
- `uv`
- Node.js 和 npm，只有需要运行 Electron 桌面壳时才必须安装
- 一个支持图片输入的 OpenAI-compatible 多模态模型 API

Python 侧核心依赖来自 [pyproject.toml](./pyproject.toml)：

- `openai`
- `pydantic`
- `python-dotenv`
- `pyautogui`
- `pygetwindow`
- `pyperclip`
- `pillow`

## 2. 进入项目目录

打开 PowerShell：

```powershell
cd H:\CUA-Lark-Agent
```

确认当前目录：

```powershell
pwd
```

期望看到：

```text
H:\CUA-Lark-Agent
```

如果项目放在别的位置，把命令里的路径换成你本机的实际路径。

## 3. 安装依赖

安装 Python 依赖：

```powershell
uv sync
```

如果要运行 Electron 桌面壳，再安装 Node 依赖：

```powershell
npm install
```

检查 CLI 是否正常：

```powershell
uv run python run.py --help
```

期望能看到类似命令列表：

```text
usage: run.py [-h] [--model MODEL] [--mode {auto,api,gui}]
              {capture,action,gui-run} ...
```

运行单元测试：

```powershell
uv run python -m unittest discover -s tests
```

期望结果：

```text
OK
```

## 4. 配置 `.env`

复制示例配置：

```powershell
Copy-Item .env.example .env
```

打开 `.env`，至少配置 GUI/VLM 这一组：

```env
GUI_VLM_MODEL=gpt-5.5
GUI_VLM_API_BASE=https://your-provider.example/v1
GUI_VLM_API_KEY=your_api_key_here
GUI_TARGET_APP=Feishu
```

模型必须支持图片输入。当前 GUI 路线会把飞书窗口截图发给 OpenAI-compatible Responses API，并使用 streaming 模式读取结果。这样可以兼容一些“非流式图片请求返回空内容”的服务。

也可以使用 OpenAI fallback 配置：

```env
OPENAI_API_BASE=https://your-provider.example/v1
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5.5
```

GUI 模型配置读取顺序是：

```text
GUI_VLM_* -> VLM_* -> OPENAI_*
```

推荐 Windows GUI 配置：

```env
GUI_MAX_STEPS=12
GUI_ACTION_PAUSE=0.5
GUI_STATE_DEBOUNCE=2
GUI_MIN_PERCEPTION_CONFIDENCE=0.25
GUI_VLM_TIMEOUT_SECONDS=90
GUI_CLEAR_MAX_DELETE_ATTEMPTS=3
GUI_DRY_RUN=0
GUI_TRACE_DIR=traces
```

不要把 `.env` 提交到 GitHub，里面包含 API Key。当前 `.gitignore` 已忽略 `.env` 和 `.env.backup*`。

## 5. 飞书窗口准备

运行 GUI 任务前：

1. 启动飞书或 Lark 桌面客户端。
2. 确认已经登录。
3. 准备一个安全测试会话，例如 `bot功能测试`。
4. 确认该会话可以接收测试消息。

Windows 窗口匹配支持这些标题关键词：

- `Feishu`
- `Lark`
- `飞书`

推荐在 `.env` 中设置：

```env
GUI_TARGET_APP=Feishu
```

如果飞书处于最小化状态，当前代码会尝试恢复窗口、激活窗口、把鼠标移动到标题栏并点击一次，然后再开始截图和执行任务。

## 6. 最小冒烟测试

### 6.1 截取飞书窗口

```powershell
uv run python run.py capture --app Feishu --name feishu_window
```

期望输出类似：

```json
{
  "path": "traces\\feishu_window.png",
  "width": 1316,
  "height": 739,
  "origin_x": 2074,
  "origin_y": 196,
  "scale_x": 1.0,
  "scale_y": 1.0
}
```

打开截图：

```powershell
Start-Process .\traces\feishu_window.png
```

确认截图里是飞书窗口，不是黑屏，也不是 VS Code 或 PowerShell。Windows 多显示器截图使用 `PIL.ImageGrab.grab(all_screens=True)`，所以飞书可以放在副屏。

### 6.2 只观察，不移动鼠标

```powershell
uv run python run.py gui-run "观察当前飞书窗口，判断当前页面是什么，不要执行任何真实操作" --dry-run --json-output --progress
```

期望结果里包含：

```json
{
  "success": true,
  "final_status": "done"
}
```

### 6.3 底层鼠标键盘测试

先 dry-run 一次，不真实点击：

```powershell
uv run python run.py action click --relative-to-app Feishu --x 100 --y 100 --dry-run
```

测试中文输入，也建议先 dry-run：

```powershell
uv run python run.py action type --text "你好，CUA 测试" --dry-run
```

确认焦点安全后再移除 `--dry-run`。

## 7. 功能测试顺序

下面这些测试建议按顺序执行，并且都带上 `--progress`，方便观察每一步模型判断和程序动作。

### 7.1 输入草稿但不发送

```powershell
uv run python run.py gui-run "在当前飞书聊天输入框输入：CUA Windows 测试成功，但不要发送" --json-output --progress
```

期望行为：

- 聚焦消息输入框
- 输入 `CUA Windows 测试成功`
- 不点击发送按钮
- 返回 `success: true`

对应 goal kind 是 `compose_message`。

### 7.2 清空草稿

```powershell
uv run python run.py gui-run "清空当前飞书聊天输入框里的草稿内容，不要发送任何消息" --json-output --progress
```

期望行为：

- 聚焦输入框左侧文本编辑区域
- 执行 `Ctrl+A`
- 执行 `Backspace`
- 校验输入框为空
- 不发送任何消息

这个流程对应 `clear_composer`。代码会避免直接拖拽选中，因为飞书里焦点不对时，`Ctrl+A` 可能会选中整个页面而不是输入框文本。

### 7.3 发送消息

建议每次用一个新的消息文本，避免和历史消息混淆：

```powershell
uv run python run.py gui-run "在当前飞书聊天中发送消息：CUA Windows 端到端测试 001" --json-output --progress
```

期望行为：

- 聚焦消息输入框
- 输入目标文本
- 点击蓝色发送按钮，或使用提交快捷键
- 根据发送后的界面状态确认成功
- 返回 `success: true`

发送成功的判断不是只看“界面像成功了”，而是要求本轮确实输入过目标文本并执行过提交动作，然后满足下面至少一个条件：

- 目标文本作为新消息出现在聊天区
- 输入框在提交后被清空

### 7.4 打开指定会话

先手动切到其他会话或其他模块，再运行：

```powershell
uv run python run.py gui-run "打开飞书中的 bot功能测试 会话" --json-output --progress
```

期望行为：

- 必要时进入消息模块
- 点击目标会话行
- 通过会话标题或输入框确认当前会话已打开
- 返回 `success: true`

### 7.5 搜索并打开会话

```powershell
uv run python run.py gui-run "在飞书中搜索 bot功能测试 并打开该会话" --json-output --progress
```

期望行为：

- 打开飞书搜索
- 输入 `bot功能测试`
- 选择匹配结果
- 确认目标会话打开

### 7.6 多步骤聊天流程

```powershell
uv run python run.py gui-run "切换到飞书消息模块，打开 bot功能测试 会话，并发送消息：CUA 多步骤测试成功 001" --json-output --progress
```

期望流程：

```text
消息模块 -> 目标会话 -> 输入框 -> 输入消息 -> 发送 -> 校验
```

### 7.7 日历模块

打开日历：

```powershell
uv run python run.py gui-run "打开飞书日历模块" --json-output --progress
```

创建日程：

```powershell
uv run python run.py gui-run "打开飞书日历，并在今天下午 6:30 创建一个日程，标题为：CUA 日历测试 0428" --json-output --progress
```

期望行为：

- 打开日历模块
- 找到今天的日期或列
- 点击目标时间段
- 输入日程标题
- 保存日程
- 在日历网格中看到新日程

重复测试日程创建时，请每次使用不同标题，否则视觉校验可能把旧日程当成当前任务结果。

## 8. Trace 和调试

每次 GUI run 都会在 `traces/` 下写入一个 trace 目录，例如：

```text
traces\20260428-133651-545475
```

常见文件：

- `step_00_observe.png`：初始截图
- `step_00_perception.json`：结构化视觉状态
- `step_01_planner.json`：动作决策
- `summary.json`：机器可读总结
- `summary.md`：人类可读总结

查看最近的 trace：

```powershell
Get-ChildItem .\traces | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

打开某次截图：

```powershell
Start-Process .\traces\<trace-dir>\step_00_observe.png
```

调试时优先看三类信息：

- 截图是不是正确窗口
- `perception.json` 是否识别到了输入框、当前会话、最新消息或日历状态
- `planner.json` 中 action 的目标和坐标是否合理

## 9. 常见问题

### 截图是黑屏

可能原因：

- 飞书在副屏，但截图逻辑只截了主屏

当前修复：

- Windows 下使用 `ImageGrab.grab(all_screens=True)` 截取所有显示器区域

检查命令：

```powershell
uv run python run.py capture --app Feishu --name feishu_window
Start-Process .\traces\feishu_window.png
```

### 清空草稿时选中了整个飞书页面

可能原因：

- `Ctrl+A` 执行时焦点不在聊天输入框里

当前修复：

- 清空草稿流程会先点击输入框左侧文本编辑区域
- 再执行 `Ctrl+A`
- 再执行 `Backspace`
- 最多重试 `GUI_CLEAR_MAX_DELETE_ATTEMPTS` 次

### 明明发送成功，程序还一直重试

可能原因：

- 视觉模型没有稳定识别最新消息
- 发送按钮目标文本里同时出现了输入框和发送按钮描述

当前修复：

- `send button`、`blue send`、`发送按钮`、`发送图标` 等明确目标会被当成提交动作
- 如果本轮已经输入目标文本并提交，且提交后输入框清空，也可以判断为发送成功

### 飞书被最小化

当前行为：

- 恢复窗口
- 激活窗口
- 点击标题栏
- 再截图并执行任务

安全测试：

```powershell
uv run python run.py gui-run "观察当前飞书窗口，判断当前页面是什么，不要执行任何真实操作" --dry-run --json-output --progress
```

### VLM 图片请求失败

当前 GUI 路线使用 [agent/gui/langchain_agents.py](./agent/gui/langchain_agents.py) 中的 streaming Responses API 图片请求。

如果你的服务支持图片，但普通 `/chat/completions` 图片请求失败，请优先配置：

```env
GUI_VLM_API_BASE=https://your-provider.example/v1
GUI_VLM_API_KEY=your_key
GUI_VLM_MODEL=your_multimodal_model
```

如果请求经常等待太久：

```env
GUI_VLM_TIMEOUT_SECONDS=30
```

## 10. 当前代码结构

GUI 相关代码主要在 [agent/gui](./agent/gui)：

- [agent/gui/capture.py](./agent/gui/capture.py)：窗口截图，Windows 下支持多显示器
- [agent/gui/window.py](./agent/gui/window.py)：窗口查找、激活、最小化恢复、坐标转换
- [agent/gui/controller.py](./agent/gui/controller.py)：真实鼠标键盘动作，中文输入走剪贴板粘贴
- [agent/gui/langchain_agents.py](./agent/gui/langchain_agents.py)：视觉理解和动作规划模型调用
- [agent/gui/goals.py](./agent/gui/goals.py)：目标分类与目标文本提取
- [agent/gui/loop.py](./agent/gui/loop.py)：观察、规划、执行、校验的主循环
- [agent/gui/prompts.py](./agent/gui/prompts.py)：VLM 感知和动作规划提示词
- [agent/gui/schema.py](./agent/gui/schema.py)：GUI 决策结构
- [agent/gui/trace.py](./agent/gui/trace.py)：trace 记录

这次 Windows 重构后，`loop.py` 不再负责所有目标解析细节。任务类型识别、消息文本提取、会话名提取、日程标题和时间提取已经拆到 `goals.py`，主循环更集中在运行状态和完成条件上。

## 11. 常用命令

运行全部测试：

```powershell
uv run python -m unittest discover -s tests
```

编译检查：

```powershell
uv run python -m compileall -q agent tests
```

截取飞书：

```powershell
uv run python run.py capture --app Feishu --name feishu_window
```

只观察不操作：

```powershell
uv run python run.py gui-run "观察当前飞书窗口，判断当前页面是什么，不要执行任何真实操作" --dry-run --json-output --progress
```

清空输入框：

```powershell
uv run python run.py gui-run "清空当前飞书聊天输入框里的草稿内容，不要发送任何消息" --json-output --progress
```

发送测试消息：

```powershell
uv run python run.py gui-run "在当前飞书聊天中发送消息：CUA Windows 端到端测试 001" --json-output --progress
```

## 12. 从 macOS 版本重构到 Windows 的主要变化

Windows 版本主要补齐了这些能力：

- 窗口激活使用 `pygetwindow`
- 飞书最小化时先恢复再截图
- Windows 多显示器截图使用 `PIL.ImageGrab.grab(all_screens=True)`
- 中文输入通过 `pyperclip` 写入剪贴板后粘贴
- `Backspace` 等单键动作使用 `pyautogui.press`
- GUI 图片请求改为 streaming Responses API
- 目标解析拆分到 `agent/gui/goals.py`
- goal kind 拆分为 `compose_message`、`clear_composer`、`send_message`、`open_chat`、`open_calendar`、`create_calendar_event`
- 完成条件会检查本轮是否真的执行过关键动作，避免把历史状态误判为成功

比赛 demo 推荐展示链路：

```text
观察飞书 -> 搜索/打开会话 -> 输入草稿 -> 清空草稿 -> 发送消息 -> 打开日历 -> 创建日程
```

这条链路能覆盖视觉理解、窗口定位、真实鼠标键盘操作、可逆草稿动作、不可逆发送动作和结果校验。
