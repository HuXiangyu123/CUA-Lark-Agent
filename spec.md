# GUI Testing Spec v0.3

> 对齐 `background.md` 与最原始赛题要求
> 核心路线：`窗口级截图 + 通用 VLM + GUI 执行`

## 1. 目标

当前版本的目标是做一个可运行的飞书桌面 GUI 测试底座，而不是做一个依赖专门 CUA 模型的黑盒 Agent。

系统需要满足：

1. 保留现有 `lark-cli` API 路线。
2. 提供真实 GUI 动作执行能力。
3. 提供基于通用 VLM 的窗口截图理解与单步决策能力。
4. 提供可追踪的 trace。

## 2. 非目标

1. 不要求专用 CUA 模型。
2. 不要求本地 OCR 引擎必须落地。
3. 不要求当前版本实现完整 API Oracle 编排。
4. 不要求当前版本实现复杂自愈。

## 3. 架构约束

### 3.1 模型侧

GUI 路线使用通用 VLM 即可：

- GPT-4o / GPT-4.1 / GPT-5.x 兼容图像输入
- Claude 3.5 Sonnet 类模型
- Qwen-VL 类模型

系统不依赖专用 CUA 模型。

### 3.2 截图侧

1. 优先只截目标窗口，不截整屏。
2. 坐标以截图图像像素为准。
3. 执行前再映射回真实屏幕坐标。
4. Retina 缩放必须显式处理。

### 3.3 执行侧

动作协议支持：

- `click`
- `double_click`
- `right_click`
- `drag`
- `scroll`
- `type`
- `hotkey`
- `wait`

## 4. 模块

### 4.1 `agent/gui/window.py`

职责：

1. 激活飞书窗口
2. 获取窗口 bounds
3. 进行相对坐标到屏幕坐标转换

### 4.2 `agent/gui/capture.py`

职责：

1. 截图目标窗口
2. 返回图像像素尺寸
3. 返回窗口在屏幕上的 origin
4. 计算 Retina scale

### 4.3 `agent/gui/prompts.py`

职责：

1. 约束感知路线输出结构化 UI state
2. 约束操作路线返回单步 GUI 动作
3. 规定坐标必须使用图像像素网格
4. 规定返回 JSON only

### 4.4 `agent/gui/langchain_agents.py`

职责：

1. 使用 LangChain `create_agent(...)` 搭建双路 agent
2. 感知路线输出结构化视觉状态
3. 操作路线输出结构化单步动作决策

### 4.5 `agent/gui/loop.py`

职责：

1. 执行 Observe -> Perceive -> Decide -> Act loop
2. 校验 VLM 返回坐标是否合法
3. 非法坐标时自动重试
4. 对视觉状态做稳定性消抖
5. 记录 trace

### 4.6 `agent/gui/controller.py`

职责：

1. 真实执行鼠标和键盘动作
2. 提供 dry-run

## 5. LangChain 双路架构

### 5.1 感知路线 agent

输入：

1. 当前窗口截图
2. 执行历史摘要
3. 当前 run state 摘要

输出：

1. `composer_text`
2. `composer_exact_match`
3. `sent_message_exact_match`
4. `blocked`
5. `confidence`
6. `evidence`

### 5.2 操作路线 agent

输入：

1. 当前窗口截图
2. 感知路线结构化结果
3. 执行历史摘要
4. 当前 run state 摘要

输出：

1. `status = continue | done | blocked`
2. `stage`
3. `success_criteria`
4. 单步 `action`

### 5.3 状态机消抖

系统对连续感知结果维护 `signature`：

1. 连续两次以上一致才视为 stable
2. 未 stable 时，不允许直接 submit
3. 未 stable 时，不允许把“发送成功”判定为 done

## 6. GUI Observation 协议

### 6.1 ScreenshotArtifact

字段：

- `path`
- `width`
- `height`
- `origin_x`
- `origin_y`
- `screen_width`
- `screen_height`
- `scale_x`
- `scale_y`

说明：

- `width / height` 是截图图像像素尺寸
- `screen_width / screen_height` 是窗口在系统坐标中的 points 尺寸
- `scale_x / scale_y` 负责把图像像素坐标映射回屏幕 points

## 7. GUI Planner 协议

VLM 必须返回：

```json
{
  "status": "continue",
  "current_state": "当前界面描述",
  "progress_assessment": "是否推进",
  "previous_step_ok": true,
  "success_criteria": "本步成功判据",
  "done_reason": "",
  "action": {
    "type": "click",
    "target": "消息输入框",
    "x": 1200,
    "y": 860
  }
}
```

约束：

1. 坐标必须落在 `0..width-1` / `0..height-1`
2. 坐标必须使用图像像素系
3. 一次只允许一个动作

## 8. 执行时序

1. 激活目标应用
2. 获取窗口 bounds
3. 截图窗口
4. 感知路线读取截图，输出结构化 UI state
5. 操作路线读取截图与运行状态，输出单步动作
6. 校验坐标是否合法
7. 把图像像素坐标映射回屏幕 points
8. 执行动作
9. 再截图并重新感知
10. 对感知结果做稳定性消抖
11. 继续下一轮或结束

## 9. 环境变量

### 9.1 API 路线

- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

### 9.2 GUI / VLM 路线

- `VLM_MODEL`
  - GUI 路线的通用多模态模型；为空时回退到 `OPENAI_MODEL`
- `VLM_API_BASE`
  - 可选，GUI 路线单独 API base
- `VLM_API_KEY`
  - 可选，GUI 路线单独 key
- `GUI_VLM_MODEL`
  - 推荐使用的 GUI 路线模型变量
- `GUI_VLM_API_BASE`
  - 推荐使用的 GUI 路线 API base 变量
- `GUI_VLM_API_KEY`
  - 推荐使用的 GUI 路线 API key 变量
- `GUI_TARGET_APP`
  - 默认 `Feishu`
- `GUI_MAX_STEPS`
  - 默认 `12`
- `GUI_ACTION_PAUSE`
  - 默认 `0.5`
- `GUI_STATE_DEBOUNCE`
  - 默认 `2`
- `GUI_ENABLE_EMOJI_HEURISTIC`
  - 默认 `0`，仅显式开启时使用固定 heuristic fallback
- `GUI_DRY_RUN`
  - 默认 `0`
- `GUI_TRACE_DIR`
  - 默认 `traces`

### 9.3 OCR 路线

- `OCR_ENABLED`
- `OCR_PROVIDER`
- `OCR_MODEL`
- `OCR_API_BASE`
- `OCR_API_KEY`

说明：

OCR 是可选辅助增强，不是当前版本的前置依赖。

## 10. 验收标准

### 10.1 基础能力

1. 能进行窗口级截图
2. 能进行真实 GUI 动作
3. 能把通用 VLM 返回的图像坐标正确映射到真实屏幕
4. 坐标非法时能自动拦截并重试

### 10.2 业务能力

在飞书桌面已登录的前提下，至少能支持：

1. 聚焦输入框
2. 输入文本
3. 发送消息
4. 记录执行 trace

## 11. 当前版本限制

1. 仍然是单步决策 loop，不是全局长程规划器
2. OCR 还未真正接入执行链
3. API Oracle 还是预留态
4. 主要针对 macOS + Feishu 桌面端
5. 发送成功验证仍然主要依赖 VLM 视觉判断与 run-state 证据，不是服务端真值校验
