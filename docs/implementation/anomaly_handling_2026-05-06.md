# Feishu Anomaly Handling Semantic Layer

Date: 2026-05-06

## Module Responsibility

This implementation practices exception handling for the active Feishu route:

```text
feishu_agent = AgentS3 + WindowsFeishuACI + Feishu semantic priors
```

The anomaly layer converts OCR-visible abnormal UI states into semantic
`product_state` flags, router recovery guidance, and runtime evidence. It does
not execute recovery steps and does not introduce a deterministic workflow or
stage machine.

## Boundaries

- In scope:
  - shared OCR keyword detection for common abnormal states;
  - semantic flags in `FeishuState.product_state`;
  - recovery-oriented tool guidance in `route_feishu_tools`;
  - semantic anomaly evidence in `S3RuntimeRecorder.runtime["anomaly_events"]`;
  - unit tests for detector, router, and recorder behavior.
- Out of scope:
  - no `Parser -> Planner -> Workflow -> Step Executor` runtime path;
  - no fixed click sequence such as "if modal, click OK";
  - no screenshot coordinate, bbox, confidence, score, resolution, or ratio
    metadata;
  - no dependency on manually supplied screenshots for this pass.

## Target Files

- `gui_agents/feishu/detectors/anomaly.py`
- `gui_agents/feishu/detectors/*_state_detector.py`
- `gui_agents/feishu/tooling/tool_router.py`
- `gui_agents/feishu/reports/s3_runtime_recorder.py`
- `tests/feishu/detectors/test_anomaly_detector.py`
- `tests/feishu/tooling/test_tool_router.py`
- `tests/feishu/reports/test_s3_runtime_recorder.py`
- `docs/implementation/README.md`

## Design

The shared detector recognizes semantic-only anomaly classes from OCR text:

- `blocking_modal_visible` with `recovery_hint=close_modal_or_wait`
- `permission_denied_visible` with `recovery_hint=request_permission`
- `loading_visible` with `recovery_hint=retry_after_load`
- `wrong_surface` with `recovery_hint=navigate_to_correct_page`

Product detectors merge these flags into the existing `product_state` during
OCR fallback. Metadata paths keep fixture-provided `product_state` unchanged.

The tool router checks anomaly flags before product-specific page guidance.
It biases `next_step_focus`, preferred tools, hints, and rationale toward
recovery observation, while still leaving action choice to the LLM loop.

The runtime recorder records anomaly events during observation capture. Events
contain only semantic evidence: step index, timestamp, product, page type,
anomaly type, and recovery hint. OCR text and visual coordinates are not stored.

## Manual Plan

- Target files: detector anomaly helper, product detectors, tool router,
  runtime recorder, tests, implementation index.
- Depends on: existing `FeishuState.product_state`, `RuntimeContext`
  optional fields, current AgentS3 recorder/report artifacts.
- Outputs: semantic anomaly flags, recovery guidance, runtime anomaly events,
  unit-test coverage.
- Verification:
  - detector/router/recorder unit tests;
  - startup self-check;
  - local CI parity through `python scripts/run_ci_checks.py`.
- Risks / rollback:
  - OCR keywords can overmatch generic modal text. Mitigation: keep flags
    semantic and advisory only, and preserve existing product-state fields.
  - Router guidance could obscure product-specific guidance. Mitigation:
    anomaly handling prepends recovery hints but does not remove normal tools.
  - Recorder should avoid duplicate events for the same step and anomaly type.
    Mitigation: dedupe on `step_index + anomaly_type`.

