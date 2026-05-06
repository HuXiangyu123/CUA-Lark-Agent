# Project State

Last updated: 2026-05-06

## Goal

Build a Windows-first Feishu desktop GUI agent on top of `Agent-S`, with the
active product route centered on:

- `classic_s3`: `AgentS3 + OSWorldACI`
- `feishu_agent`: `AgentS3 + WindowsFeishuACI`

The current codebase no longer treats deterministic `planner/ -> workflow`
stage machines as the product runtime.

## Active Runtime

Current effective Feishu runtime:

```text
Natural language / user instruction
  -> AgentS3 LLM loop
  -> WindowsFeishuACI
  -> Feishu semantic priors:
     pages / detectors / tool_router / verifiers / reports
```

Current implications:

- `feishu_agent` is the active Feishu-specific route.
- `FeishuWorker` and product `*_workflow.py` runtime controllers have been removed.
- Page metadata for new product slices is constrained to semantic facts only.
- `Track ABCD` now acts as an agentic knowledge/tool layer, not a fixed executor.

## Requirement Snapshot

This section checks the current repository state against `docs/项目需求.md`.

### Must-Have Capabilities

1. Visual perception: largely implemented at the semantic layer.
   Evidence:
   - Page descriptors and state detectors exist for `IM`, `Docs`, `Calendar`,
     `Base`, and `VC`.
   - Startup and Feishu test suite cover registry/detector imports and fixture
     compatibility.

2. Semantic understanding: partially implemented.
   Current status:
   - `IM` text send-message parsing is stable.
   - `Docs` and `VC` still have parser coverage for structured testcase inputs.
   - `Calendar` and `Base` no longer compile fixed workflows and are expected to
     run through `feishu_agent` semantic guidance instead.

3. Autonomous operation: partially implemented.
   Current status:
   - `IM` has the strongest runtime support, including Feishu-specific click/type
     helpers and grounded fallback.
   - Browser-aware helpers exist for Docs-related browser surfaces.
   - `Calendar`, `Base`, and `VC` currently rely more on semantic tool guidance
     than on fully validated live task execution.

4. State verification: partially implemented.
   Current status:
   - `IM`, `Docs`, and `Base` assertions are implemented in
     `AssertionVerifier`.
   - `VC` now has dedicated runtime assertions for home/start/join/invite end
     states.
   - `Calendar` detector coverage exists, but stronger calendar-specific
     verifier depth is still missing.

5. Evaluation report: partially to substantially implemented.
   Current status:
   - Per-run artifacts are generated through `S3RuntimeRecorder`,
     `ReportBuilder`, and `ArtifactManager`.
   - `summary.json`, `report.md`, `actions.jsonl`, and screenshot persistence
     are in place.
   - Batch-level success-rate aggregation and an offline interactive evaluation
     dashboard are implemented; trend comparison is still missing.

### Milestone Snapshot

| Milestone | Requirement target | Current status |
| --- | --- | --- |
| `M0` | Agent startup baseline | Done |
| `M1` | 5 single-step actions | Mostly done at runtime/tool level |
| `M2` | 1 product, 3 end-to-end flows | Partially done; IM main path exists, but 3 stable E2E flows are not yet complete |
| `M3` | 2+ products stable runnable | Partially done; 5 products have semantic/domain coverage, but stable live runnable coverage still lags |
| `M4` | structured evaluation system | Partially done; per-run artifacts, batch aggregation, and offline dashboard exist; regression runner and trend comparison are still missing |
| `M5` | 1-2 advanced features | Partially done; exception handling and self-heal primitives exist, others remain open |

## Product Coverage

### IM

Current status: strongest and closest to production use.

Implemented:

- IM page descriptors and detectors
- search-panel and shell-search state handling
- Feishu-specific IM typing/click helpers
- tool routing for composer, send, search, and emoji fallback
- IM assertion verification
- runtime artifact recording

Not yet complete:

- broader IM workflow matrix beyond the current text send path
- richer live-validated paths such as file send, image send, `@` mention, and
  emoji end-to-end completion

### Docs

Current status: semantic/domain slice mostly present, runtime completeness not
yet at IM level.

Implemented:

- Docs page descriptors
- Docs state detector
- title/body-related verifier branches
- historical parser support

Missing or weaker:

- product-specific tool-router branch comparable to IM/Calendar/VC
- live end-to-end validation in the active `feishu_agent` route

### Calendar

Current status: semantic/domain slice present, runtime still shallow.

Implemented:

- Calendar page descriptors
- Calendar detector
- semantic-only fixture constraints
- Calendar tool-router guidance
- Calendar verifier branches: `calendar_home_ready`, `calendar_event_modal_ready`

Missing:

- validated end-to-end create-event runtime path

### Base

Current status: semantic/domain slice present after cleanup.

Implemented:

- Base page descriptors
- Base detector
- Base tool-router guidance
- semantic-only metadata constraints
- explicit rejection of fixed workflow parsing and fixed coordinate locating

Missing:

- validated end-to-end live runtime path
- dedicated batch evaluation around Base tasks

### VC

Current status: in progress and currently the main remaining app-level repair
item.

Implemented:

- VC page descriptors
- VC detector
- VC tool-router guidance
- semantic-only fixture constraints
- dedicated VC verifier branches
- runtime goal extraction and Track D final-state verification
- agentic helper tools for start/join/invite-related controls
- invite-popover semantic detection for active-meeting flows

Missing:

- stable live runtime validation for start/join/invite flows on the launcher
- broader VC task coverage such as camera/microphone toggles and richer invite
  completion paths

## Auto Evaluation Status

### Implemented

- `tests.test_agent_startup` as session startup gate
- `tests.test_launcher_env_config` for launcher env routing
- `scripts/run_ci_checks.py` for local/GitHub CI parity
- `scripts/check_constraints.py` for architecture guardrails
- `S3RuntimeRecorder` passive runtime capture
- `ArtifactManager` stable artifact persistence
- `ReportBuilder` for `summary.json` and `report.md`
- `EvaluationAggregator` batch aggregation from `summary.json` artifacts
- `tests/eval_suite/feishu_eval_suite.json` read-only test case manifest (17 cases, 5 products; includes 5 cross-window candidates)
- `scripts/build_feishu_eval_report.py` CLI wrapper for batch evaluation
- `evaluation_dashboard.html` offline interactive evaluation dashboard
- `dashboard_server.py` localhost read-only report portal with launcher entry
- Live E2E evidence pack from existing run artifacts:
  `live_e2e_evidence.json` and `live_e2e_evidence.md`

### Output Currently Available

Per-run outputs under `artifacts/test_runs/<run_id>/`:

- `summary.json`
- `report.md`
- `actions.jsonl`
- `screenshots/`

Batch outputs under `artifacts/evaluation/`:

- `evaluation_summary.json`
- `evaluation_report.md`
- `evaluation_dashboard.html`
- `live_e2e_evidence.json`
- `live_e2e_evidence.md`

### Still Missing

- ~~aggregate success-rate reporting across runs~~ → done: `evaluation_aggregator.py` + `build_feishu_eval_report.py`
- ~~dashboard / visualization layer~~ -> done: `evaluation_dashboard.html`
- ~~Live E2E evidence pack generation~~ -> done: artifact completeness and
  assertion-pass evidence from `artifacts/test_runs/*`
- regression runner over a test suite (manifest created, batch runner deferred)
- trend comparison between runs

## Advanced Feature Status

Checked against the advanced requirements in `docs/项目需求.md`.

Preliminary implementation plan for 4 low-risk features is available at
`docs/implementation/advanced_features_preliminary_plan.md`.

### 1. Exception handling

Status: partially implemented (preliminary plan ready).

Evidence:

- detectors preserve `modal_type`
- tool routing includes popup/dialog-aware branches for IM, VC, Docs, Calendar
- runtime can classify recognition/location/action/verification/runtime failures

Gap:

- no unified anomaly detection keywords in detector fallback paths
- no `recovery_hint` guidance injection in tool_router

### 2. Self-healing execution

Status: partially implemented (preliminary plan ready).

Evidence:

- `Worker` supports `reflection_mode=on_failure`
- `_detect_plan_failure()` detects "Behind:", "no effect", "still empty" etc.
- `last_step_failed` flag escalates reasoning effort
- `feishu_click(...)` can prepare a grounded fallback for icon-only controls
- verifier supports OCR fallback in all assertion branches

Gap:

- no recovery guidance injected into Worker prompt when `last_step_failed=True`
- no `recovery_attempts` tracking in RuntimeContext

### 3. Cross-product linked testing

Status: partially implemented at testcase/evidence-probe level.

Current state:

- five cross-window eval candidates are now listed in
  `tests/eval_suite/feishu_eval_suite.json`
- covered handoffs: Docs -> IM, Calendar -> IM, Base -> Docs, VC -> IM,
  Docs -> Calendar
- these cases are semantic manifest entries only; no deterministic runtime
  controller or ordered step sequence is introduced

Gap:

- no active linked runtime runner
- live pass evidence still depends on real Feishu desktop runs and artifact
  review through `live_e2e_evidence.*`

### 4. Testcase auto generation

Status: not implemented (deferred).

Current state:

- no generator from Feishu docs, recordings, or product specs
- deferred: scope explosion risk

### 5. Mixed locator strategy

Status: design placeholder only (deferred).

Current state:

- `VisionLocator` is active (runtime-region-only bounds)
- `AccessibilityLocator` / `HybridLocator` remain documented placeholders
- deferred: environment compatibility not yet stable

### 6. Multi-turn orchestration

Status: partially implemented (preliminary plan ready).

Evidence:

- `AgentS3` adjusts next action from current screenshot
- `build_dynamic_guidance()` provides per-step tool guidance
- reasoning effort and reflection escalate after failures
- `FeishuToolRecommendation` already carries state_summary, next_step_focus, preferred_tools

Gap:

- per-turn state/guidance block not yet formatted into Worker prompt
- no concise turn summary injection before each action generation

### 7. Record and replay

Status: not implemented (preliminary plan ready — semantic trace only).

Current state:

- screenshots and action logs are recorded via S3RuntimeRecorder
- `summary.json`, `report.md`, `actions.jsonl` are generated
- no semantic trace or replay draft output yet
- plan commits to semantic-only trace (no coordinate scripts)

## Current Priority

Primary repair items completed:

- VC verifier branches (6 assertions) implemented
- Docs tool routing branch implemented
- `relative_bounds` / quantitative coordinates purged from all feishu modules
- `LocatorResult` purified to `action_target` (semantic-only)
- `RuntimeContext` cleaned of workflow remnants (`intent`/`params` replaces `workflow`/`workflow_params`)

Recommended next order:

1. Step 0: freeze RuntimeContext shared fields (`recovery_attempts`, `anomaly_events`, `semantic_steps`)
2. 异常场景处理 (anomaly detection + recovery hints)
3. 自愈式执行 (recovery prompt injection)
4. 多轮对话编排 (per-turn state/guidance block)
5. 录制回放语义轨迹版 (semantic_trace.json + replay_draft.md)
6. Calendar verifier branches (only major gap remaining in product coverage)
7. Regression runner and trend comparison (M4)

## Historical Drift Notes

- Many `docs/implementation/*` files still contain historical references to
  deterministic workflows. They are useful as implementation records, not as
  current runtime contracts.
- `docs/implementation/feishu_agent_migration_remove_workflows_2026-05-06.md`
  is the cutover record for the current architecture.
- For session-level delivery details, see
  `docs/process/development_log_2026-05-06.md`.
