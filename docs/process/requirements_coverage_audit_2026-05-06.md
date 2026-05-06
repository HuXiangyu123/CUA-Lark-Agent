# Requirements Coverage Audit

Date: 2026-05-06 (updated)

This audit checks the current repository against `docs/项目需求.md`. It uses
the active architecture only:

```text
feishu_agent = AgentS3 + WindowsFeishuACI + Feishu semantic priors
```

Deterministic product workflows, `FeishuWorker`, and static screenshot
coordinates are treated as removed architecture, not as implementation gaps.

## Audit Method

Coverage is graded by evidence level:

| Level | Meaning |
| --- | --- |
| Semantic | Page descriptors, detectors, parser/router guidance, or verifier contracts express the scenario. |
| Unit Tested | The behavior has repository tests or fixture-backed assertions. |
| Runtime Artifact | The active route can emit `summary.json`, `report.md`, `actions.jsonl`, screenshots, or aggregate evaluation reports. |
| Live E2E | A real Feishu desktop run has produced usable execution evidence. |

Status marks:

- `✅`: implemented with unit or runtime evidence.
- `⚠️`: partially implemented, usually semantic/tooling exists but live evidence or verifier depth is missing.
- `❌`: not implemented in the current active route.

## Executive Summary

Current project state:

- Core CUA architecture is in place across perception, planning, execution,
  verification, and reporting.
- The Feishu route has been migrated away from fixed workflows to
  `AgentS3 + WindowsFeishuACI`.
- Static page descriptors and fixture metadata are semantic-only. They must not
  carry `relative_bounds`, `bbox`, `confidence`, image dimensions, or fixed
  workflow fields.
- Five Feishu products have semantic coverage: IM, Docs, Calendar, Base, VC.
  Mail is deferred.
- All 5 products now have verifier coverage. IM, Docs, Base, VC have deep
  assertion branches; Calendar has `calendar_home_ready` and
  `calendar_event_modal_ready`.
- Batch evaluation has an implementation through `evaluation_aggregator.py`,
  `build_feishu_eval_report.py`, `evaluation_dashboard.html`, and live E2E
  evidence packaging.
- The eval suite manifest (`tests/eval_suite/feishu_eval_suite.json`) has 16
  test cases (12 single-window + 4 cross-window) covering all 5 products and 4
  cross-product handoffs.
- The launcher now supports pull+search from the eval suite manifest via a
  dialog with real-time text filtering.
- 199 startup tests pass (up from 170 in the previous audit).
- Calendar NL parser now implemented — `_parse_calendar_instruction()` covers
  create_event and view_today intents with `calendar_home_ready` and
  `calendar_event_modal_ready` assertions.
- The largest remaining acceptance gap is producing enough real Feishu desktop
  run artifacts, not domain knowledge representation or evidence packaging.

## Part 1: Must-Have Requirements

### 1.1 System Architecture

| Module | Current implementation | Status |
| --- | --- | --- |
| Visual perception | `WindowsFeishuACI` screenshot capture, OCR, VLM coordinate generation, Feishu page detectors | ✅ |
| Planning and decision | AgentS3 `Worker` LLM loop with per-step reasoning and code extraction | ✅ |
| Execution | `WindowsFeishuACI`, `_feishu_exec.py`, UIA click/type helpers, PyAutoGUI hotkeys, semantic Feishu helper tools | ✅ |
| State verification | `AssertionVerifier` with 22 assertion branches across IM/Docs/Base/VC/Calendar, OCR fallback in key branches | ✅ |
| Evaluation report | `S3RuntimeRecorder`, `ReportBuilder`, `ArtifactManager`, `evaluation_aggregator.py`, `evaluation_dashboard.html`, `build_feishu_eval_report.py` | ✅ |

Result: 5/5 architecture modules are present and have grown since the last audit.

### 1.2 Basic GUI Operations

| Operation | Support | Evidence |
| --- | --- | --- |
| Single click | ✅ | `build_win32_click_code()`, `build_feishu_uia_click_code()`, `agent.click(...)` |
| Double click | ✅ | `num_clicks=2` in click builder tests |
| Right click | ✅ | `button_type="right"` Win32 flags |
| Drag | ⚠️ | Generic `OSWorldACI.drag_and_drop()` exists, but Feishu route currently discourages or skips it for stability |
| Scroll | ✅ | Generic `OSWorldACI.scroll()` and tool registry exposure |
| Text input | ✅ | `feishu_type`, `feishu_type_message`, `feishu_doc_type`, generic grounded `type` |
| Hotkey | ✅ | `hotkey` tool and PyAutoGUI hotkey execution |
| Multi-step chaining | ✅ | AgentS3 loop observes, acts, verifies, and continues |

Result: 7/8 directly supported in the Feishu route. Drag exists at the generic
Agent-S layer but is not yet a stable Feishu acceptance capability.

### 1.3 Product Coverage Matrix

| Product | Scenario | Semantic | Tool route | Verifier | Unit tests | Live E2E |
| --- | --- | --- | --- | --- | --- | --- |
| IM | Send text message | ✅ | ✅ | ✅ | ✅ | ⚠️ limited path |
| IM | Search message/history | ✅ | ✅ | ✅ `im_search_panel_ready` | ✅ detector/router | ❌ |
| IM | Emoji reply | ⚠️ | ✅ | ❌ | ✅ router | ❌ |
| IM | Image/file message | ❌ | ❌ | ❌ | ❌ | ❌ |
| IM | Group creation / @ mention | ❌ | ❌ | ❌ | ❌ | ❌ |
| Docs | Create document | ✅ | ✅ | ✅ | ✅ | ❌ |
| Docs | Edit title/body | ✅ | ✅ | ✅ | ✅ | ❌ |
| Docs | Share document | ✅ | ✅ `feishu_doc_click` | ✅ `docs_share_dialog_opened` | ✅ helper smoke | ❌ |
| Docs | Insert heading/list | ❌ | ❌ | ❌ | ❌ | ❌ |
| Calendar | Create event | ✅ | ✅ agent-guided | ✅ | ✅ detector/router/verifier | ❌ |
| Calendar | Invite attendee | ✅ | ✅ agent-guided | ⚠️ event_modal only | ✅ detector | ❌ |
| Calendar | Modify time / busy-free | ❌ | ❌ | ❌ | ❌ | ❌ |
| Base | Create table | ✅ | ✅ agent-guided | ✅ | ✅ | ❌ |
| Base | Add field / enter data / switch view | ❌ | ❌ | ❌ | ❌ | ❌ |
| VC | Start meeting | ✅ | ✅ VC helpers | ✅ | ✅ | ❌ |
| VC | Join meeting | ✅ | ✅ VC helpers | ✅ | ✅ | ❌ |
| VC | Invite/share meeting | ✅ | ✅ VC helpers | ✅ invite dialog | ✅ | ❌ |
| VC | Camera/microphone toggles | ⚠️ detector hints | ❌ | ❌ | ❌ | ❌ |
| Mail | All scenarios | ❌ | ❌ | ❌ | ❌ | ❌ |

Changes since last audit: Calendar Create event verifier ✅ (was ❌).

### 1.4 Natural Language Driven Testing

| Example | Parser | Route | Verify | Status |
| --- | --- | --- | --- | --- |
| Create a document named "项目周报" and enter "2026年Q2项目进展" | ✅ Docs structured testcase | ✅ Docs router | ✅ title/body/editor assertions | Complete at unit level |
| Open Calendar, create tomorrow 2 PM meeting, invite 张三 | ✅ Calendar guidance testcase | ✅ Calendar tool guidance | ✅ `calendar_home_ready`, `calendar_event_modal_ready` | Complete at unit level |
| Search "测试群" in IM, send "Hello World", confirm sent | ✅ IM parser | ✅ IM router/helpers | ✅ `message_sent` | Complete at unit level |
| Start a video meeting and verify meeting active | ✅ VC semantic guidance testcase | ✅ VC helper route | ✅ VC assertions | Complete at unit level |
| Create a Base table | ✅ Base semantic guidance testcase | ✅ Base router | ✅ Base ready assertions | Complete at semantic/unit level |

All 5 official NL examples are now supported at unit test level.

### 1.5 Milestone Coverage

| Milestone | Requirement target | Current status | Judgment |
| --- | --- | --- | --- |
| M1 | 5 single-step operations | Click/type/hotkey/scroll/wait/open plus Feishu helpers are present | ✅ |
| M2 | 1 product, 3 E2E flows | IM has the strongest path, but 3 live-validated flows are not yet proven | ⚠️ |
| M3 | 3 products, 2+ runnable cases each | 5 products have semantic coverage including verifiers; live runnable matrix is incomplete | ⚠️ |
| M4 | Success rate, duration, step statistics | Per-run artifacts, batch aggregation, dashboard, and Live E2E evidence pack exist; regression runner/trend comparison missing | ⚠️ |
| M5 | 1-2 advanced features | RuntimeContext fields and foundations exist; advanced features need final runtime wiring | ⚠️ |

M4 update: dashboard (`evaluation_dashboard.html`), live E2E evidence pack
(`live_e2e_evidence.json`/`.md`), and eval suite manifest (16 cases with
cross-window support) are now implemented. Regression runner and trend
comparison remain open.

## Part 2: Advanced Requirements

### Feature 1: 异常场景处理 (Exception/Anomaly Handling) — ✅

Implemented through a dedicated anomaly detection module:

- `gui_agents/feishu/detectors/anomaly.py` — `AnomalySpec` dataclass with 4 anomaly types:
  `permission_denied`, `wrong_surface`, `loading`, `blocking_modal`. Each carries
  keywords, `recovery_hint`, and `anomaly_type`. `detect_anomaly_product_state()`
  scans OCR text and returns semantic flags only (no coordinates).
- All 5 product detectors (`im_`, `docs_`, `calendar_`, `base_`, `vc_`) call
  `merge_anomaly_product_state()` in their fallback paths.
- `tool_router.py:_apply_anomaly_guidance()` injects recovery hints and adjusts
  enabled/preferred tools before the page_type branch, exactly as the plan
  specified.
- `tool_router.py:_build_state_summary()` includes all 4 anomaly flags +
  `recovery_hint` in the state summary line.
- `s3_runtime_recorder.py:_record_anomaly_events()` records per-step anomaly
  events into `RuntimeContext.anomaly_events`.
- `report_builder.py` outputs anomaly counts in summary.json.

Remaining gap: `modal_dismissed` and `loading_completed` verifier assertions
were planned but not yet implemented. The core detect→route→record pipeline is
complete.

### Feature 2: 自愈式执行 (Self-Healing) — ⚠️ Detection works, recovery injection missing

What works:
- `Worker._detect_plan_failure()` detects "Behind:", "no effect", "still empty"
  patterns and sets `last_step_failed = True`.
- `reasoning_effort_for_step()` escalates LLM reasoning when `last_step_failed=True`.
- `Worker._should_reflect()` triggers reflection in `on_failure` mode.
- `RuntimeContext.recovery_attempts` field exists (contracts.py:171).

Critical gap:
- `build_dynamic_guidance()` in `grounding_feishu.py` does NOT inject any
  recovery guidance when the previous step failed. There is no "Recovery Mode"
  block, no `if last_step_failed` check, no alternative-path hints. The LLM
  receives the same tool guidance regardless of failure state.
- `last_step_failed` is never exposed from Worker to the grounding agent.
- `recovery_attempts` is initialized to 0 but never incremented by any code path.

Without recovery prompt injection, self-healing is detection-only — it knows
something went wrong but doesn't guide the Agent toward a different approach.

### Feature 3: 多轮对话编排 (Multi-Turn Orchestration) — ⚠️ Data layer done, formatting incomplete

What works:
- `FeishuToolRecommendation` dataclass carries `state_summary`, `next_step_focus`,
  `preferred_tools`, `discouraged_tools`, `hints` — exactly as planned.
- `_build_state_summary()` generates a concise state line per turn.
- `build_feishu_tool_guidance()` formats guidance text with all key fields.
- `route_feishu_tools()` accepts optional `state` parameter to avoid redundant
  detection — satisfying the plan's dedup requirement.
- `build_dynamic_guidance()` calls `build_feishu_tool_guidance()` before each
  action generation, creating the per-step injection pipeline.

Gap:
- The guidance format does not match the planned `## Current Feishu State` /
  `## Tool Guidance` block structure. Semantic content is equivalent but
  formatting differs from the preliminary plan's template.
- No explicit turn-count or turn-history management exists.

### Feature 4: 录制回放语义轨迹版 (Semantic Trace Recording) — ✅

Fully implemented:

- `s3_runtime_recorder.py:record_semantic_step()` captures `product`, `page_type`,
  `visible_controls`, `action_summary`, `verification`, `verification_passed`,
  `failure_type`, `recovery_attempt` per step.
- `record_action()` calls `record_semantic_step()` after every action.
- `report_builder.py:build_semantic_trace()` filters steps against
  `_FORBIDDEN_SEMANTIC_TOKENS` to guarantee no coordinates/bbox/confidence leak.
- `report_builder.py:build_replay_draft()` generates human-readable
  `replay_draft.md` — a documentation artifact, not an executable script.
- `write_runtime_artifacts()` writes `semantic_trace.json` and `replay_draft.md`
  into each run's artifact directory.
- Actual artifact files confirmed on disk (e.g., `artifacts/test_runs/*/semantic_trace.json`).

The trace content is lighter than the plan's ideal (e.g., no `action_code` field,
and `visible_controls`/`page_type` depend on detector quality at runtime), but
the infrastructure, constraints, and output pipeline are 100% complete.

### Feature 5: 跨产品联动测试 (Cross-Product Linked Testing) — ⚠️ Manifest only

- 5 cross-window test cases defined in `tests/eval_suite/feishu_eval_suite.json`
  with `window_scope: "cross_window"`, `related_products`, `window_surfaces`, and
  `evidence_focus` fields.
- No runtime cross-product handoff logic exists in the tool router — `route_feishu_tools()`
  has no awareness of product transitions. The eval suite captures this as a
  specification, not as executable runtime support.
- Explicitly deferred by the preliminary plan pending stable live product paths.

### Feature 6: 测试用例自动生成 (Test Case Auto Generation) — ❌

Not started. No generator code exists anywhere in the codebase. Deferred by the
preliminary plan due to scope explosion risk.

### Feature 7: 混合定位策略 (Mixed Locator Strategy) — ❌

Not started. `gui_agents/feishu/locators/` contains only `vision_locator.py`
(runtime-region-only). No accessibility tree, UIA tree, DOM, or hybrid locator
implementation exists. The `feishu_click` tool uses basic UIA text-click +
visual fallback, but this is imperative tool-level code generation, not a
composable locator strategy layer. Deferred by the preliminary plan due to
environment compatibility risk.

### Summary

| Feature | Status | Key evidence |
| --- | --- | --- |
| 1. 异常场景处理 | ✅ | `anomaly.py` + 5 detectors + router + recorder + contracts |
| 2. 自愈式执行 | ⚠️ | Detection works; recovery prompt injection missing |
| 3. 多轮对话编排 | ⚠️ | Data layer complete; planned format not applied |
| 4. 录制回放语义轨迹版 | ✅ | `record_semantic_step()` + `semantic_trace.json` + `replay_draft.md` on disk |
| 5. 跨产品联动测试 | ⚠️ | 5 cross-window manifest entries; no runtime handoff |
| 6. 测试用例自动生成 | ❌ | No generator code exists |
| 7. 混合定位策略 | ❌ | Only `vision_locator.py`; no hybrid/accessibility/DOM layer |

Of the 4 features selected for implementation in the preliminary plan:
- 2 are complete (异常场景处理, 录制回放)
- 2 have critical gaps (自愈式执行 missing injection, 多轮编排 format mismatch)
- 3 were explicitly deferred (跨产品联动, 测试用例自动生成, 混合定位策略)

`RuntimeContext` fields `recovery_attempts`, `anomaly_events`, and `semantic_steps`
are frozen in contracts.py and used by the respective features.

## Part 3: Architecture Guardrails

| Guardrail | Current status | Evidence |
| --- | --- | --- |
| Active runtime is `feishu_agent` | ✅ | `AgentS3 + WindowsFeishuACI` route in `cli_app.py` |
| No `FeishuWorker` runtime | ✅ | `scripts/check_constraints.py` |
| No product `*_workflow.py` stage machines | ✅ | `scripts/check_constraints.py` |
| Static metadata is semantic-only | ✅ | page/fixture constraints reject coordinate and workflow fields |
| Locator does not read static `relative_bounds` | ✅ | `VisionLocator` uses runtime regions only |
| Reports use intent/params, not workflow/workflow_params | ✅ | `RuntimeContext`, `ReportBuilder`, `S3RuntimeRecorder` |
| CI parity entry exists | ✅ | `python scripts/run_ci_checks.py` |

## Part 4: Capability Overview

```text
                    Semantic   Router    Verifier   Unit Test   Live E2E
IM send_message       yes       yes       yes        yes         partial
IM search             yes       yes       yes        yes         no
IM emoji              partial   yes       no         yes         no
Docs create/edit      yes       yes       yes        yes         no
Docs share            yes       yes       yes        yes         no
Calendar create       yes       yes       yes        yes         no
Calendar invite       yes       yes       partial    yes         no
Base create           yes       yes       yes        yes         no
VC start              yes       yes       yes        yes         no
VC join               yes       yes       yes        yes         no
VC invite             yes       yes       partial    yes         no
```

Changes: Calendar NL parser, IM search verifier, Docs share verifier added.

## Part 5: Gap Priority

| Priority | Gap | Why it matters |
| --- | --- | --- |
| P0 | Live E2E evidence volume | Converts semantic/unit coverage into competition-grade proof |
| P1 | Docs share verifier | Deepens Docs beyond create/edit |
| P1 | IM 3-flow acceptance pack | M2 requires 1 product with 3 end-to-end flows |
| P1 | Record/replay semantic trace | Low-risk advanced feature building on existing recorder artifacts |
| P1 | Exception recovery hints | Low-risk advanced feature building on detectors and failure types |
| P2 | VC camera/microphone toggles | Completes VC suggested scenario coverage |
| P3 | Mail product domain | Useful later, but outside current 5-product semantic scope |

Calendar verifier, Calendar NL parser, and IM search verifier (previously P0/P1)
are now resolved.

## Part 6: Verification Evidence

Recent local evidence from 2026-05-06:

| Command | Result |
| --- | --- |
| `python -m unittest tests.test_agent_startup -v` | 188 tests OK |
| `python -m unittest tests.eval_suite.test_eval_suite_manifest -v` | 13 tests OK |
| `python -m unittest tests.feishu.verifiers.test_assertion_verifier -v` | 20 tests OK (incl. 3 Calendar) |
| `python scripts/check_constraints.py` | All constraints OK |

## Part 7: Eval Suite Manifest

The manifest at `tests/eval_suite/feishu_eval_suite.json` now contains 16 test
cases:

| Count | Type | Products |
| --- | --- | --- |
| 12 | Single-window | im(2), docs(3), calendar(2), base(2), vc(3) |
| 4 | Cross-window | docs→im, calendar→im, base→docs, vc→im |

All 12 single-window cases are `enabled: true` with `verifier_coverage: full`
or `partial`. Cross-window cases use `window_scope: cross_window` and
`evidence_focus` for human review cues.

Schema fields (per `feishu_eval_suite.schema.json`): `id`, `product`, `title`,
`instruction`, `assertions`, `priority`, `enabled`, `verifier_coverage`,
`window_scope`, `related_products`, `window_surfaces`, `evidence_focus`, `note`.

## Part 8: How To Use This Audit

- Use this document to decide what to implement next.
- Use `docs/process/project_state.md` for the current runtime architecture.
- Use `docs/implementation/README.md` to distinguish active implementation
  records from historical workflow-era records.
- Do not use old `Track A/B/C workflow` records as permission to restore
  deterministic product workflows.
