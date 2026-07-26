from pathlib import Path

ROOT = Path(__file__).parents[2]
AUDIT = (ROOT / "sentinel" / "v2_consolidation_audit.md").read_text(encoding="utf-8")
FLAGS = (
    "OPERATIONAL_TELEMETRY_HUB_ENABLED",
    "PERSISTENT_CONTROL_BOUNDARY_ENABLED",
    "V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED",
    "V2_OPERATIONAL_OBSERVABILITY_ENABLED",
    "CONTROLLED_RUNTIME_ACTIVATION_ENABLED",
    "V2_CANARY_ENABLED",
    "V2_AUTHORITY_MIGRATION_ENABLED",
    "FINAL_CONTROL_PLANE_READINESS_ENABLED",
    "V2_TRUST_EVALUATION_ENABLED",
    "ACTIVATION_GATEWAY_ENABLED",
    "CANARY_OBSERVATION_ENABLED",
    "RUNTIME_CANARY_ENABLED",
    "RUNTIME_TRIAL_ENABLED",
)


def test_relevant_flags_are_documented_and_not_removed():
    for flag in FLAGS:
        assert flag in AUDIT


def test_consolidation_does_not_enable_productive_flags():
    control_files = tuple((ROOT / "sentinel").glob("*/control.py"))
    for path in control_files:
        source = path.read_text(encoding="utf-8")
        assert "_ENABLED = True" not in source
