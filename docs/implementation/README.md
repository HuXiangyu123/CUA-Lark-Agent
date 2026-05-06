# Implementation Records Index

Date: 2026-05-06

This directory contains implementation records, not a single source of truth.
For current architecture and module contracts, read:

1. `docs/process/project_state.md`
2. `docs/process/requirements_coverage_audit_2026-05-06.md`
3. `docs/spec/feishu_gui_agent_technical_spec.md`
4. `docs/interfaces/feishu_gui_agent_interfaces.md`

## Current Runtime Rule

The active Feishu route is:

```text
feishu_agent = AgentS3 + WindowsFeishuACI + Feishu semantic priors
```

Do not use older records in this directory to restore `FeishuWorker`,
`planner/workflow_selector.py`, or product `*_workflow.py` stage machines.

## Current / Active Records

These records describe the current agentic route or current guardrails:

| Document | Purpose |
| --- | --- |
| `technical_debt_dead_code_cleanup_2026-05-06.md` | Static metadata cleanup, locator contract cleanup, workflow-field removal. |
| `feishu_agent_migration_remove_workflows_2026-05-06.md` | Cutover record from deterministic Feishu workflows to `feishu_agent`. |
| `feishu_agent_docs_router_and_parser_contract_2026-05-06.md` | Docs parser/router contract in the agentic route. |
| `feishu_batch_evaluation_2026-05-06.md` | Batch evaluation aggregation and report CLI. |
| `feishu_evaluation_dashboard_2026-05-06.md` | Offline interactive dashboard for aggregate evaluation artifacts. |
| `evaluation_dashboard_feishu_blue_cn_2026-05-06.md` | Chinese blue-white Feishu-styled evaluation dashboard UI refresh. |
| `evaluation_dashboard_unified_process_quality_2026-05-06.md` | Unified `/dashboard` route, report links, and process-quality metrics for evaluation review. |
| `dashboard_report_visual_iteration_2026-05-06.md` | Per-run report visual refresh, clickable dashboard rows, and compact run/task labels. |
| `report_metrics_defaults_and_icon_report_2026-05-06.md` | Stable process-quality metric defaults, runtime reflection capture, and icon-led per-run report page. |
| `runtime_incremental_artifacts_and_abort_2026-05-06.md` | Incremental run artifacts, runtime stdout log, finalize error files, and launcher manual-abort evidence. |
| `calendar_fixture_normalization_and_runtime_logging_2026-05-06.md` | Calendar fixture English normalization, quick-add/full-create separation, and lighter live runtime logging. |
| `calendar_new_fixture_practice_2026-05-06.md` | Practice record for classifying and configuring newly added Calendar screenshots. |
| `live_e2e_evidence_pack_2026-05-06.md` | Live E2E artifact completeness and acceptance evidence pack. |
| `cross_window_eval_cases_2026-05-06.md` | Cross-window eval suite cases for VLM-driven product handoffs. |
| `launcher_semantic_replay_viewer_2026-05-06.md` | Launcher tab for viewing semantic replay artifacts without executing replay. |
| `launcher_dashboard_server_2026-05-06.md` | Launcher button and localhost report portal for converted evaluation artifacts. |
| `launcher_default_execution_mode_feishu_agent_2026-05-06.md` | Launcher default execution mode changed to `feishu_agent` while preserving manual `classic_s3` selection. |
| `advanced_runtime_context_field_freeze_2026-05-06.md` | Optional advanced-feature fields on `RuntimeContext`. |
| `advanced_features_preliminary_plan.md` | Low-risk advanced feature plan. |
| `anomaly_handling_2026-05-06.md` | Semantic exception handling through anomaly flags, recovery guidance, and runtime events. |
| `anomaly_report_evidence_2026-05-06.md` | Carries anomaly runtime events into reviewable reports, traces, and replay drafts. |
| `vc_agentic_tools_runtime_stabilization_2026-05-06.md` | VC helper tools and runtime stabilization. |
| `vc_m4_runtime_verification_integration_2026-05-06.md` | VC final verification integration. |
| `s3_feishu_agent_track_d_artifacts_2026-05-06.md` | Runtime artifact recording through the agentic route. |
| `s3_feishu_runtime_guidance_and_fallback_fix_2026-05-06.md` | Runtime guidance and fallback repair for Feishu route. |
| `audit_remediation_track_cd_connectivity_2026-05-06.md` | Track C/D connectivity remediation without restoring fixed workflows. |
| `calendar_track_abcd_create_event_2026-05-06.md` | Calendar semantic/domain slice under the agentic route. |
| `base_track_abcd_2026-05-06.md` | Base semantic/domain slice; historical statements about static bounds are superseded by cleanup record. |
| `vc_track_abcd_video_meeting_2026-05-06.md` | VC semantic/domain slice; historical workflow target references are superseded by migration record. |

## Historical / Superseded Records

These records are useful for understanding how the repository evolved, but they
must not be treated as current runtime design:

| Document | Superseded assumption |
| --- | --- |
| `track_a_foundation_2026-05-05.md` | Mentions `WorkflowPlan`, `workflow_selector.py`, and `feishu_worker` as future consumers. |
| `track_b_mvp_analysis_2026-05-05.md` | Mentions future `workflows/` and `feishu_worker` consumers. |
| `track_b_closeout_and_track_c_entry_2026-05-05.md` | Track C entry language predates the agentic runtime cutover. |
| `docs_track_abcd_create_doc_2026-05-06.md` | Preserves older `WorkflowPlan` / workflow selector terminology as historical context. |
| `docs_track_b_pages_and_detector_2026-05-06.md` | Mentions coarse `relative_bounds`; static bounds are now removed. |
| `s3_feishu_agentic_tools_refactor_2026-05-05.md` | Describes an in-progress refactor and rollback option around old worker compatibility. |
| `launcher_dual_mode_s3_feishu_integration_2026-05-05.md` | Pre-cutover launcher integration record; current execution modes are `classic_s3` and `feishu_agent`. |

When a historical record conflicts with current code or source-of-truth docs,
prefer current code, `project_state`, `spec`, `interfaces`, and
`scripts/check_constraints.py`.

## Maintenance Rule

- New implementation docs should include module responsibilities, boundaries,
  target files, plan, verification, and risks.
- If a doc is superseded, update this index instead of silently deleting it.
- If a doc contains historical references to removed architecture, add a short
  note in the doc or list it in the Historical section here.
