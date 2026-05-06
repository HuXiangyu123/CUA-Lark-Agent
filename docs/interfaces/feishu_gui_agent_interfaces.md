# 飞书 GUI Agent Interface Doc

## 1. 文档定位

本文档定义飞书 GUI Agent 内部模块接口、输入输出契约和阶段边界。

这不是开放平台 API 文档，而是项目内部模块接口文档。

相关文档：

- [文档索引](../README.md)
- [主方案](../feishu_gui_agent_master_plan.md)
- [PRD](../product/feishu_gui_agent_prd.md)
- [Technical Spec](../spec/feishu_gui_agent_technical_spec.md)

## 2. 契约使用原则

1. 任何跨模块协作都先遵守本文档约定，不允许绕过接口直连内部实现。
2. 需要并行开发时，先冻结字段与返回值，再拆分任务。
3. 发生破坏性变更时，必须同步更新 `Technical Spec` 和调用方。

## 3. TestCase Parser Interface

### 输入

- `instruction: str`

### 输出

```python
{
    "id": "tc_im_send_message_001",
    "product": "im",
    "title": "在测试群发送消息并验证发送成功",
    "preconditions": ["飞书桌面端已登录"],
    "steps": [
        {
            "step_id": "step_1",
            "action": "open_chat",
            "target": "测试群",
            "payload": None,
            "assertion": "chat_opened"
        },
        {
            "step_id": "step_2",
            "action": "type_message",
            "target": "message_input",
            "payload": {"text": "Hello World"},
            "assertion": "message_input_contains_text"
        },
        {
            "step_id": "step_3",
            "action": "send_message",
            "target": "send_button",
            "payload": None,
            "assertion": "message_sent"
        }
    ],
    "assertions": ["chat_title_matched", "message_sent"]
}
```

## 4. FailureType Contract

共享失败分类枚举：

```python
FailureType = Literal[
    "recognition",
    "location",
    "action",
    "verification",
    "timeout",
    "precondition",
]
```

约定：

- `failure_type` 用于标准化统计和聚合。
- `failure_reason` 用于补充具体失败原因，可为自然语言或结构化短句。
- `failure_reason` 不能替代 `failure_type`。

## 5. Tool Guidance Interface

该输出结构统一命名为 `FeishuToolGuidance`。它是给 `feishu_agent` 的语义先验，不是固定执行计划。

### 输入

- `testcase: dict`
- `state: FeishuState | None`
- `observation: dict | None`

### 输出

```python
{
    "product": "im",
    "intent": "send_message",
    "reason": "matched product=im and task intent=send_message",
    "params": {
        "chat_name": "测试群",
        "message_text": "Hello World"
    },
    "preferred_tools": ["click", "type", "hotkey"],
    "next_step_focus": "message_input",
    "verification_hints": ["chat_title_matched", "message_sent"],
    "entry_assertions": ["chat_title_matched"],
    "preconditions": ["飞书桌面端已登录"],
    "failure_type": None,
    "failure_reason": None
}
```

### `FeishuToolGuidance` 类型别名

```python
FeishuToolGuidance = dict
```

说明：

- `Tool Router` 保留并透传 `preconditions`，但不负责最终执行检查。
- `Tool Router` 若在执行前失败，`failure_type` 必须复用共享 `FailureType` 枚举。
- `Tool Router` 只给出工具子集、业务参数提示、下一步关注点和验证提示，不产出 ordered steps。
- 若未命中产品意图，`intent` 为空，`failure_reason` 需要给出可审阅原因。
- 所有执行必须继续经过 `feishu_agent = AgentS3 + WindowsFeishuACI`。

## 5.1 Shared Id Contracts

最小共享标识建议：

```python
ActionId = Literal[
    "open_chat",
    "focus_message_input",
    "type_message",
    "send_message",
    "open_docs_home",
    "open_docs_new_menu",
    "select_docs_document_type",
    "select_blank_doc_template",
    "type_doc_title",
    "type_doc_body",
]

TargetId = Literal[
    "global_search_entry",
    "conversation_list_item",
    "conversation_search_entry",
    "conversation_search_close_button",
    "conversation_search_result_item",
    "search_result_item",
    "message_input",
    "send_button",
    "docs_new_card",
    "docs_document_option",
    "docs_blank_doc_card",
    "docs_title_input",
    "docs_body_editor",
]

AssertionId = Literal[
    "chat_title_matched",
    "message_input_contains_text",
    "message_sent",
    "docs_home_ready",
    "docs_new_menu_opened",
    "docs_template_gallery_ready",
    "doc_editor_ready",
    "doc_title_contains_text",
    "doc_body_contains_text",
    "calendar_home_ready",
    "calendar_event_modal_ready",
    "calendar_quick_add_ready",
    "calendar_create_surface_ready",
]
```

约定：

- `Parser`、`Tool Router`、`Locator`、`Verifier` 共享同一套 `ActionId / TargetId / AssertionId`。
- 新增共享标识前，先更新本文档，再允许并行开发模块引用。

## 6. StateDetector Interface

### 输入

- `observation: dict`

### 输出

```python
from dataclasses import dataclass


@dataclass
class FeishuState:
    page_type: str
    product: str
    chat_name: str | None
    message_input_visible: bool
    send_button_visible: bool
    search_box_visible: bool
    modal_type: str | None
    last_error_banner: str | None
    product_state: dict
```

说明：

- `FeishuState` 是基础状态模型。
- `product_state` 承载子产品特有状态，例如：
  - `Docs`: `{"doc_title": "...", "editor_ready": True}`
  - `Calendar`: `{"selected_date": "2026-05-05", "time_picker_visible": True}`

## 7. Locator Interface

统一定位接口建议：

```python
class BaseLocator:
    def locate(self, target: str, state, observation, page_context=None) -> dict:
        ...
```

`page_context` 约定：

```python
{
    "page_descriptor": PageDescriptor,
    "active_region": str | None,
    "runtime_region": dict | None,
}
```

### 输出

```python
{
    "matched": True,
    "strategy": "runtime_region",
    "page_id": "im_chat_main",
    "target": "message_input",
    "action_target": {
        "kind": "point",
        "point": [512, 720],
        "source": "runtime_observation"
    }
}
```

字段约定：

- 静态 `PageDescriptor` / fixture 不提供坐标。
- `action_target` 只能来自当前 runtime observation 的即时定位结果。
- `page_id` 应与 `PageDescriptor.page_id` 对齐
- 若定位失败但页面识别成功，`page_id` 返回当前页面的 `PageDescriptor.page_id`
- 若页面也无法可靠识别，`page_id` 返回 `None`

失败输出示例：

```python
{
    "matched": False,
    "strategy": "runtime_region",
    "page_id": None,
    "target": None,
    "action_target": None,
    "failure_type": "location",
    "failure_reason": "anchor text not found in current viewport"
}
```

实现类型：

- `VisionLocator`：当前默认运行链路
- `AccessibilityLocator`：仅保留接口占位，当前默认入口不启用
- `HybridLocator`：仅保留接口占位，当前默认入口不启用

截图 fixture / 页面语义抽取约束：

- 静态 fixture 只保存语义事实，例如可见控件、页面类型、弹窗状态、文字锚点。
- 静态 fixture 不保存 `bbox`、`relative_bounds`、`confidence`、图片宽高等量化图像指标。
- 坐标和置信度只允许作为 runtime locator 的即时结果，不允许沉淀为产品域语义数据。

## 8. FeishuACI Interface

```python
class FeishuACI:
    def open_chat(self, chat_name: str): ...
    def ensure_in_chat(self, chat_name: str): ...
    def focus_message_input(self): ...
    def clear_message_input(self): ...
    def type_message(self, text: str): ...
    def send_message(self): ...
    def recover_from_modal_or_wrong_page(self): ...
```

当前里程碑说明：

- `FeishuACI` 是语义动作抽象，不要求当前代码已经完整实现上述专用方法
- 当前默认入口 `gui_agents/s3/cli_app.py` 使用的是 `gui_agents/s3/agents/grounding.py` 中的 `OSWorldACI`
- 因此默认主线只应假设通用动作存在，例如 `open`、`click`、`type`、`hotkey`、`wait`
- 若后续恢复或重新接线 Feishu / Windows 专用 helper（含 UIA 路线），应视为可选扩展，不得默认写成已接入事实，除非入口与调用链已同步更新

## 9. AgentS3 Execution Interface

当前执行统一通过 `cli_app.py` 的 `run_agent()` 函数驱动 `AgentS3` LLM agent loop，不再存在独立的 `FeishuWorker` 类。

### `run_agent` 签名

```python
def run_agent(
    agent: AgentS3,
    instruction: str,
    scaled_width: int,
    scaled_height: int,
    max_steps: int = 15,
    recorder: S3RuntimeRecorder | None = None,
) -> None:
    ...
```

### `S3RuntimeRecorder` (via Track D)

`S3RuntimeRecorder` 被动记录 AgentS3 每步 action 和最终状态，并产出 Track D 产物：

```python
class S3RuntimeRecorder:
    def start(self, instruction: str) -> None: ...
    def record_observation(self, step_index: int, obs: dict) -> None: ...
    def record_action(self, step_index: int, code: str, status: str, failure_reason: str | None = None) -> None: ...
    def finalize(self, final_status: str, final_failure_reason: str | None = None) -> dict | None: ...
```

### `finalize` 输出产物

```text
artifacts/test_runs/<run_id>/
  screenshots/
  actions.jsonl
  summary.json
  report.md
```

### 前置条件策略

当前 M0-M2 阶段允许部分前置条件通过人工保证，未自动化校验的项在运行结果中标记为 `assumed`，避免误报为已验证。

## 10. Deprecated Workflow Interface

产品级 Workflow Interface 已废弃。

约束：

- 不再定义 `BaseWorkflow`、`next_step()`、`is_done()` 等 runtime 阶段机接口。
- 不得新增 `*_workflow.py` 并把用户任务转成固定步骤序列执行。
- 历史文档中的 workflow 只能作为归档参考，不作为当前接口契约。
- 当前运行时统一通过 `AgentS3 + WindowsFeishuACI` 的 LLM loop 决策下一步 action。

## 11. Verifier Interface

```python
class BaseVerifier:
    def verify_step(self, expected: dict, state, observation, runtime_context) -> dict: ...
    def verify_case(self, testcase: dict, runtime_context) -> dict: ...
```

### `verify_step` 输出

```python
{
    "passed": True,
    "step_id": "step_2",
    "assertion": "message_input_contains_text",
    "evidence": ["ocr:text=Hello World"],
    "failure_type": None,
    "failure_reason": None
}
```

### `verify_case` 输出

```python
{
    "passed": True,
    "total_steps": 3,
    "passed_steps": 3,
    "failed_steps": 0,
    "failure_type": None,
    "failure_reason": None
}
```

## 12. ActionLog Interface

```python
{
    "timestamp": "2026-05-04T15:30:04+08:00",
    "step_id": "step_2",
    "stage": "TYPE_MESSAGE",
    "action": "type_message",
    "target": "message_input",
    "params": {"text": "Hello World"},
    "status": "executed"
}
```

## 13. StepResult Interface

```python
{
    "step_id": "step_2",
    "stage": "TYPE_MESSAGE",
    "action": "type_message",
    "target": "message_input",
    "status": "passed",
    "locator_result": {
        "matched": True,
        "page_id": "im_chat_main"
    },
    "verification_result": {
        "passed": True,
        "assertion": "message_input_contains_text"
    },
    "failure_type": None,
    "failure_reason": None
}
```

## 14. ReportBuilder Interface

```python
class ReportBuilder:
    def build_summary(self, testcase: dict, runtime_context: dict) -> dict: ...
    def build_markdown(self, summary: dict) -> str: ...
```

### `build_summary` 输出

```python
{
    "task_id": "tc_im_send_message_001",
    "product": "im",
    "intent": "send_message",
    "status": "passed",
    "steps": 3,
    "duration_sec": 18.4,
    "assertions": [
        {"name": "chat_title_matched", "passed": True},
        {"name": "message_sent", "passed": True}
    ],
    "failure_type": None,
    "failure_reason": None
}
```

## 15. RuntimeContext Interface

```python
{
    "run_id": "2026-05-04_153000",
    "status": "passed",
    "intent": "send_message",
    "params": {"chat_name": "测试群", "message_text": "Hello World"},
    "page_id": "im_chat_main",
    "precondition_results": [],
    "action_logs": [],
    "screenshots": [],
    "step_results": [],
    "failure_type": None,
    "failure_reason": None,
    "started_at": "2026-05-04T15:30:00+08:00"
}
```

约定：

- `action_logs` 使用 `ActionLog` 结构。
- `step_results` 使用 `StepResult` 结构。
- 顶层 `failure_type` 表示整次运行的 case 级失败归因。
- 若失败发生在执行前，顶层 `failure_type` 直接记录该失败。
- 若失败发生在步骤执行中，顶层 `failure_type` 取导致整次运行终止的首个失败步骤的 `step_results[].failure_type`。
- 若整次运行成功，顶层 `failure_type` 为 `None`。
- `ReportBuilder`、`review`、`regression runner` 统一消费 `RuntimeContext`，不要直接依赖 `AgentS3` 私有内部变量。

## 16. Maintenance Interfaces

```python
class ScreenshotRecorder:
    def record_page(self, page_id: str) -> None: ...


class AnchorValidator:
    def validate_page(self, page_id: str, screenshot: bytes) -> dict: ...
    def suggest_refresh(self, page_id: str) -> list[str]: ...
```

## 17. 产物接口

统一产物目录：

```text
artifacts/
  test_runs/
    <run_id>/
      screenshots/
      actions.jsonl
      summary.json
      report.md
```

`summary.json` 最小字段：

```python
{
    "task_id": "tc_im_send_message_001",
    "product": "im",
    "intent": "send_message",
    "status": "passed",
    "steps": 3,
    "duration_sec": 18.4,
    "assertions": [],
    "failure_type": None,
    "failure_reason": None
}
```

## 18. 接口变更规则

1. 新增字段优先向后兼容，避免直接改名或改语义。
2. `steps[]`、`preferred_tools`、`next_step_focus`、`verification_hints` 属于稳定核心字段，不应随模块实现随意漂移。
3. 任一并行开发模块若修改接口，必须在合并前完成调用方联调和文档更新。

## 19. Track B/C 补充说明（2026-05-05）

本节补充当前实现已经使用、但前文尚未单独写明的两点：

### IM 会话内搜索子状态

`im_chat_search_panel` 可以通过 `FeishuState.product_state` 表达多个子状态，包括：

- 空搜索面板
- 已出现结果列表
- 结果已选中，主聊天区已跳转到对应消息上下文

“结果已选中并跳转到上下文” 不引入新的 `page_id`，仍保持：

- `page_id = "im_chat_search_panel"`
- `page_type = "chat_search_panel"`

推荐的 `product_state` 提示字段：

```python
{
    "search_result_context_in_chat_visible": True,
    "selected_conversation_search_result_text": "...",
}
```

### Track C 当前定位

Track C 不再提供运行时 Workflow。当前实现只保留 verifier / assertion 能力，并将成功判定作为 `feishu_agent` 的验证提示。

该定位复用现有共享 `ActionId / TargetId / AssertionId`，不新增固定阶段机契约。
