# Cross-Window Eval Cases

Date: 2026-05-06

## Module Role

Generate cross-window Feishu GUI test cases for the existing read-only eval
suite manifest.

These cases are designed for the active VLM-driven route:

```text
feishu_agent = AgentS3 + WindowsFeishuACI + Feishu semantic priors
```

They are task candidates and evidence probes. They are not workflow plans and
must not be compiled into ordered runtime steps.

## Boundaries

In scope:

- Add manifest fields that describe cross-window scope semantically:
  `window_scope`, `related_products`, `window_surfaces`, and `evidence_focus`.
- Add several cross-window candidate cases covering Docs, Calendar, Base, VC,
  and IM handoffs.
- Add manifest tests to ensure cross-window cases are explicit, semantic, and
  do not contain coordinate or fixed-step metadata.

Out of scope:

- No live execution runner.
- No deterministic cross-window controller.
- No `steps`, ordered plans, coordinates, bbox, confidence, screenshot
  dimensions, or static locator hints.
- No new verifier assertions in this change.

## Manual Plan

Target files:

- `tests/eval_suite/feishu_eval_suite.schema.json`
- `tests/eval_suite/feishu_eval_suite.json`
- `tests/eval_suite/test_eval_suite_manifest.py`
- `docs/implementation/cross_window_eval_cases_2026-05-06.md`

Depends on:

- Existing eval suite manifest and validation tests.
- Existing verifier assertion IDs.
- Existing Live E2E evidence packaging for later artifact review.

Outputs:

- Optional schema fields for cross-window task metadata.
- At least 4 cross-window test cases with natural-language instructions.
- Unit tests ensuring cross-window cases are present and semantic-only.

Verification:

- `python -m unittest tests.eval_suite.test_eval_suite_manifest -v`
- `python scripts/check_constraints.py`
- `python -m unittest tests.test_agent_startup -v`
- `python scripts/run_ci_checks.py`

Risks and rollback:

- Risk: cross-window metadata accidentally becomes a hidden execution plan.
  Mitigation: schema only accepts semantic facts and tests reject `steps`,
  coordinates, and ordered/action-sequence fields.
- Risk: final-state assertions cannot fully validate intermediate product
  states yet.
  Mitigation: use `evidence_focus` to tell reviewers what semantic trace and
  screenshots should prove; do not claim full verifier coverage where final
  verification is partial.
- Rollback: remove added manifest cases and optional schema fields; runtime code
  is unaffected.
