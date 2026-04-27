# 技术栈选型 v0.3

## 1. 结论

当前项目应采用：

`Python + 通用 VLM + PyAutoGUI + Feishu API 辅助验证`

不应把“是否有专门 CUA 模型”作为前置条件。

## 2. 技术栈

| 模块 | 选型 | 说明 |
|---|---|---|
| 主语言 | Python 3.12 | 当前最稳 |
| GUI 执行 | PyAutoGUI | 鼠标、键盘、滚动、拖拽 |
| 窗口管理 | AppleScript / System Events | 激活窗口、获取 bounds |
| 截图 | macOS `screencapture` | 原生稳定 |
| 图像理解 | 通用 VLM + LangChain agent | 双路 agent：感知路线 + 操作路线 |
| OCR | 可选 | 当前先预留 |
| API 辅助 | `lark-cli` | Setup / Oracle / Cleanup |
| Trace | JSON + Markdown + PNG | 本地可追踪 |

## 3. 当前工程建议命名

### API 路线

- `OPENAI_MODEL`

### GUI 路线

- `VLM_MODEL`
- `VLM_API_BASE`
- `VLM_API_KEY`
- `GUI_VLM_MODEL`
- `GUI_VLM_API_BASE`
- `GUI_VLM_API_KEY`
- `GUI_TARGET_APP`
- `GUI_MAX_STEPS`
- `GUI_ACTION_PAUSE`
- `GUI_STATE_DEBOUNCE`
- `GUI_ENABLE_EMOJI_HEURISTIC`
- `GUI_DRY_RUN`
- `GUI_TRACE_DIR`

### OCR 路线

- `OCR_ENABLED`
- `OCR_PROVIDER`
- `OCR_MODEL`
- `OCR_API_BASE`
- `OCR_API_KEY`

## 4. 为什么这样选

1. 赛题要求的是系统闭环，不是指定某个专用模型。
2. 通用 VLM 已足够承担页面理解与单步动作规划。
3. LangChain `create_agent(...)` 可以把“感知路线”和“操作路线”显式拆开，便于后续扩展状态机和工具链。
4. 真正的工程难点在窗口截图、坐标映射、动作执行、验证链路，而不在模型名。
5. `lark-cli` 已经是现成资产，应该继续保留。
