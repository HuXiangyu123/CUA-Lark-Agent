# Live E2E Evidence Pack

Date: 2026-05-06

## Module Role

This module closes the current Live E2E evidence gap marked in
`docs/process/requirements_coverage_audit_2026-05-06.md`.

It does not execute Feishu tasks. It validates and aggregates evidence produced
by real `feishu_agent = AgentS3 + WindowsFeishuACI` runs under
`artifacts/test_runs/<run_id>/`.

## Boundaries

In scope:

- Inspect each run directory that already contains `summary.json`.
- Check whether required review artifacts exist:
  `summary.json`, `report.md`, `actions.jsonl`, and screenshots.
- Check whether the run is an active Feishu AgentS3 run and whether final
  assertions passed.
- Write a machine-readable `live_e2e_evidence.json` and human-readable
  `live_e2e_evidence.md` next to existing batch evaluation outputs.
- Include semantic trace and replay draft presence as optional evidence facts.

Out of scope:

- No live Feishu execution runner.
- No deterministic workflow or replay executor.
- No screenshot coordinate, bbox, confidence, or image-dimension metadata.
- No automatic claim that a unit-test artifact is a real desktop run unless the
  artifact set passes the evidence checks.

## Key Interactions

```text
artifacts/test_runs/*/
  summary.json
  report.md
  actions.jsonl
  screenshots/
  semantic_trace.json       optional
  replay_draft.md           optional
    -> build_live_e2e_evidence()
    -> live_e2e_evidence.json
    -> live_e2e_evidence.md
```

`EvaluationAggregator` remains offline and read-only with respect to run
artifacts. It only writes aggregate evidence files under the evaluation output
directory.

## Manual Plan

Target files:

- `gui_agents/feishu/reports/evaluation_aggregator.py`
- `scripts/build_feishu_eval_report.py`
- `tests/feishu/reports/test_evaluation_aggregator.py`
- `docs/implementation/live_e2e_evidence_pack_2026-05-06.md`
- `docs/implementation/README.md`
- `docs/process/project_state.md`
- `docs/process/requirements_coverage_audit_2026-05-06.md`

Depends on:

- Existing per-run artifacts from `S3RuntimeRecorder` / `ReportBuilder`.
- Existing batch evaluation output path in `write_evaluation_report()`.
- Existing semantic trace and dashboard changes in the current workspace.

Outputs:

- `build_live_e2e_evidence(summaries)`
- `build_live_e2e_markdown(evidence)`
- `live_e2e_evidence.json`
- `live_e2e_evidence.md`
- CLI prints for the new evidence files

Verification:

- Unit tests for complete and incomplete evidence packs.
- CLI test confirms the new paths are printed.
- `python -m unittest tests.feishu.reports.test_evaluation_aggregator -v`
- `python scripts/check_constraints.py`
- `python -m unittest tests.test_agent_startup -v`
- `python scripts/run_ci_checks.py`

Risks and rollback:

- Risk: artifact checks become too strict and hide useful failed-run evidence.
  Mitigation: report both artifact completeness and acceptance pass status.
- Risk: evidence pack is mistaken for execution automation.
  Mitigation: no runner, no replay executor, no ordered action contract.
- Rollback: remove the two new output files from `write_evaluation_report()`;
  existing `evaluation_summary.json`, `evaluation_report.md`, and
  `evaluation_dashboard.html` remain unchanged.
