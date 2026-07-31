# Observability Decommission — Deletion Manifest

Date: 2026-07-31
Parent: `docs/observability_decommission/01_dependency_report.md`

## Decision

Full decommission: remove the 4 legacy observability stacks AND the obs-connected
v2 control-plane cluster (closed dependency loop, zero live-runtime references,
documented dead/dormant in `docs/final_certification/phase0_inventory.md`).

Live packages **excluded** (still used): `sentinel/advisory`, `sentinel/local_model`,
`sentinel/monitoring`.

## Packages removed (45 obs-connected + 2 core files)

```
sentinel/operational_telemetry_hub/
sentinel/v2_operational_observability/
sentinel/core/observability.py
sentinel/core/observability_center.py
sentinel/activation_gateway/          sentinel/adapters/
sentinel/application_discovery_v2/    sentinel/authority_safety_layer/
sentinel/authorization_canary/        sentinel/authorization_manager/
sentinel/canary_environment/          sentinel/canary_observation/
sentinel/consent_manager/             sentinel/contract_adapters/
sentinel/contracts/                   sentinel/controlled_runtime_activation/
sentinel/cutover_validation/          sentinel/decision_long_term_evaluation/
sentinel/decision_shadow_validation/  sentinel/evidence_integrity/
sentinel/execution_boundary/          sentinel/execution_planner/
sentinel/executor_sandbox/            sentinel/final_control_plane_readiness/
sentinel/limited_execution_v2/        sentinel/persistent_control_boundary/
sentinel/policy_engine/               sentinel/policy_v2_shadow/
sentinel/promotion_validation/        sentinel/recommendation_engine/
sentinel/runtime_canary/              sentinel/runtime_equivalence_validation/
sentinel/runtime_isolation/           sentinel/runtime_replay_validation/
sentinel/runtime_trial/               sentinel/runtime_v2_controlled/
sentinel/sandbox_engine/              sentinel/shadow/
sentinel/shadow_decision_orchestrator/ sentinel/shadow_runtime_real/
sentinel/simulation_engine/           sentinel/stability_validation/
sentinel/tool_gateway/                sentinel/v2_authority_migration/
sentinel/v2_authority_readiness/      sentinel/v2_operational_evidence_storage/
sentinel/v2_trust_evaluation/         sentinel/v2_unified_pipeline/
```

## Obsolete tests removed

159 files under `sidecar/tests/` (all imports of deleted packages, boundary/audit
tests over deleted module paths, and the 2 `ObservabilityService`/`ObservabilityCenter`
legacy tests). Full list tracked separately for the git commit.

## Validation after deletion

- `python -m pytest sidecar/tests/observability` — modern engine suite still green
- `python -m pytest tests/production` — FASE 6 certification still PASS
- No remaining `import sentinel.operational_telemetry_hub` / `v2_operational_observability`
  / `from sentinel.core.observability` anywhere
