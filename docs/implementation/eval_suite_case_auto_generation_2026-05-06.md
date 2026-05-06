# Eval Suite Case Auto Generation

Date: 2026-05-06

## Module Role

This pass implements the first practical slice of Feature 6: test case auto
generation.

The target is not runtime workflow generation. The target is a reproducible
generator for the read-only Feishu eval suite manifest used by review,
launcher selection, and future evaluation orchestration.

Active runtime remains:

```text
feishu_agent = AgentS3 + WindowsFeishuACI + Feishu semantic priors
```

The generator belongs to the testcase/evaluation preparation layer, not the
execution path.

## Scope Decision

The requirement originally mentions generating structured test cases from
Feishu product docs or recordings. Recording understanding is still high-risk
and out of scope for this pass.

This implementation narrows the feature to a low-risk, shippable subset:

- structured seed spec
- generator module
- deterministic manifest output
- validation tests
- CLI/script entry for regeneration

This moves the project from "no generator exists" to "doc/seed-driven manifest
generation exists".

## Boundary

In scope:

- generate `tests/eval_suite/feishu_eval_suite.json` from a smaller source spec
- keep current eval suite fields and semantics
- validate assertions, products, priorities, coverage, and cross-window review
  metadata during generation
- add tests proving the checked-in manifest is reproducible

Out of scope:

- recording/video parsing
- screenshot understanding for case generation
- runtime workflow generation
- fixed ordered execution chains
- changing launcher execution behavior

## Constraints

Must preserve:

- semantic-only eval suite metadata
- no `steps`, `ordered_steps`, `action_sequence`, coordinates, bbox, or image
  quantitative fields in generated eval cases
- compatibility with current launcher manifest loader
- compatibility with current eval suite schema/tests

Must not introduce:

- product workflow executors
- runtime controller logic
- hidden deterministic plans inside manifest metadata

## Key Interactions

```text
seed spec
  -> gui_agents/feishu/testcases/eval_suite_generator.py
      -> generated eval suite manifest
          -> tests/eval_suite/feishu_eval_suite.json
          -> launcher manifest picker
          -> evaluation/review tooling
```

## Target Files

- `gui_agents/feishu/testcases/eval_suite_generator.py`
- `gui_agents/feishu/testcases/__init__.py`
- `scripts/generate_feishu_eval_suite.py`
- `tests/eval_suite/feishu_eval_suite_seed.json`
- `tests/feishu/testcases/test_eval_suite_generator.py`
- optionally `tests/eval_suite/feishu_eval_suite.json` if regeneration output
  differs
- this implementation record

## Manual Plan

Target files:

- generator module, seed spec, generation script, generator tests

Depends on:

- current eval suite manifest contract
- current known verifier assertion IDs
- launcher read-only manifest consumption

Outputs:

- deterministic case generator for eval suite manifest
- seed-driven regeneration command
- regression test proving generated output matches the checked-in manifest

Verification:

- `python -m unittest tests.feishu.testcases.test_eval_suite_generator tests.eval_suite.test_eval_suite_manifest -v`
- `python scripts/generate_feishu_eval_suite.py --check`
- `python scripts/check_constraints.py`
- `python -m unittest tests.test_agent_startup -v`

Risks / rollback:

- Risk: generator bakes in fixed workflow or step-chain data.
  Mitigation: generator only emits manifest-level semantic metadata and tests
  reject workflow-like fields.
- Risk: generated output drifts from launcher expectations.
  Mitigation: keep output schema identical to current manifest and add parity
  test.
- Rollback: keep checked-in manifest, remove generator module/script/tests.
