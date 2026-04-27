文档名称：CUA-Lark GUI 智能测试 SOP

版本：v0.3

## 核心原则

1. GUI 是主执行路径。
2. API 是辅助验证路径。
3. 视觉理解采用“截图 + 通用 VLM”，不假设必须接入专门 CUA 模型。
4. OCR 是可选增强，不是前置依赖。
5. 所有动作必须可追踪、可复盘。

---

# 1. 测试用例设计 SOP

## 1.1 用例字段

每条用例建议包含：

- `case_id`
- `product`
- `instruction`
- `priority`
- `preconditions`
- `params`
- `gui_steps_expected`
- `api_setup`
- `api_oracle`
- `cleanup`
- `max_steps`
- `timeout_sec`
- `risk_level`
- `allow_recovery`

## 1.2 用例示例：IM 发送消息

- `case_id`: `im_send_message_001`
- `product`: `IM`
- `instruction`: 在飞书 IM 中搜索“bot功能测试”，发送消息“hello-world”，并确认发送成功。
- `preconditions`:
  - 飞书已登录测试账号
  - 群聊存在
  - 测试账号在群内
- `params`:
  - `group_name=bot功能测试`
  - `message=hello-world`
- `api_setup`:
  - 可选查询目标群是否存在
  - 记录 `start_time`
- `gui_steps_expected`:
  - 打开 IM
  - 搜索目标群
  - 进入群会话
  - 聚焦输入框
  - 输入消息
  - 发送消息
- `api_oracle`:
  - 可选查询最近消息中是否出现 `hello-world`

---

# 2. 执行前环境准备 SOP

## 2.1 账号与权限

1. 使用独立测试账号。
2. 不用个人真实账号跑冒烟。
3. `lark-cli` 登录有效。
4. 终端具备 macOS 屏幕录制权限。
5. 终端具备 macOS 辅助功能权限。

## 2.2 GUI 环境

1. 飞书桌面客户端已打开。
2. 飞书位于前台或可被激活。
3. 窗口未被大面积遮挡。
4. 弹窗尽量关闭。
5. 初始化 `trace` 目录。

## 2.3 基线记录

执行前记录：

1. 当前平台
2. 当前前台应用
3. 飞书窗口 bounds
4. 初始截图
5. 当前时间戳

---

# 3. 单条用例执行 SOP

## Step 1：加载目标

输入：

- 自然语言目标
- 或结构化测试用例

输出：

- 标准化目标对象

通过标准：

- 目标明确
- 参数完整
- 风险等级明确

## Step 2：执行 API Setup（可选）

目标：

使用 API 做环境准备，不代替 GUI 业务动作。

可以做：

1. 查询群、文档、日历对象是否存在
2. 记录开始时间
3. 记录对象 ID

不能做：

1. 直接用 API 发送目标消息
2. 直接用 API 完成 GUI 用例主体动作

## Step 3：GUI Precheck

目标：

确认飞书处于可操作状态。

动作：

1. 激活飞书窗口
2. 获取窗口 bounds
3. 截图窗口
4. 判断窗口是否可见

通过标准：

1. 飞书窗口存在
2. 飞书窗口成功激活
3. 截图可读

## Step 4：Observe

目标：

获取当前 GUI 状态。

动作：

1. 截图目标窗口
2. 可选 OCR
3. VLM 理解页面状态
4. 识别候选交互区域

输出：

- `ScreenshotArtifact`
- `current_state`
- `candidate_elements`

说明：

当前版本不要求专门 CUA 模型；通用 VLM 即可承担页面理解。

## Step 5：Plan

目标：

让通用 VLM 只返回一步最安全的 GUI 动作。

要求：

1. 返回 JSON
2. 坐标基于截图图像像素
3. 坐标必须在截图边界内
4. 只允许一个动作

输出：

- `GuiDecision`

## Step 6：Validate Planner Output

目标：

在执行前拦截无效动作。

检查项：

1. JSON 是否可解析
2. `action.type` 是否合法
3. 坐标是否越界
4. 文本输入或快捷键参数是否完整

失败处理：

1. 让 VLM 重新返回动作
2. 把越界原因作为 retry note 回传给模型

## Step 7：Coordinate Mapping

目标：

把截图图像像素坐标映射为真实屏幕 points 坐标。

关键点：

1. 目标窗口截图可能是 Retina 图像
2. 图像像素不等于系统鼠标坐标
3. 必须使用 `scale_x / scale_y` 进行转换

## Step 8：Execute GUI Action

目标：

执行真实鼠标或键盘动作。

支持动作：

1. 点击
2. 双击
3. 右键
4. 拖拽
5. 滚动
6. 文本输入
7. 快捷键
8. 等待

## Step 9：Post-Action Observe

目标：

动作后重新截图并评估状态变化。

动作：

1. 再次获取飞书窗口 bounds
2. 再次截图
3. 再次进行页面理解

## Step 10：GUI Verifier

目标：

根据最新截图判断动作是否推进目标。

方式：

1. VLM 语义判断
2. 可选 OCR 文本匹配
3. 简单规则判断

## Step 11：API Oracle（可选）

目标：

用飞书 API 做最终业务校验。

适用场景：

1. IM 发送消息
2. Calendar 创建事件
3. Docs 创建或编辑文档

## Step 12：生成报告

输出至少包含：

1. `final_status`
2. `step_count`
3. `trace_dir`
4. `screenshots`
5. `planner_outputs`
6. `action_results`

---

# 4. 当前版本工程结论

当前版本系统定义应当是：

`Screenshot + General VLM + GUI Executor + Optional OCR + API Oracle`

而不是：

`必须有专门 CUA 模型才能开始做`
