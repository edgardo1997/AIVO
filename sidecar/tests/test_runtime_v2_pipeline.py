from dataclasses import dataclass

from sentinel.runtime_v2_controlled import (
    ControlledRuntimeDiagnostics,
    ControlledRuntimePipeline,
    RuntimeV2Control,
)


@dataclass
class _ShadowOutput:
    legacy_summary: dict
    planner_result: dict
    discovery_result: dict
    policy_result: dict
    authorization_result: dict


class _ShadowPipeline:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.received = None

    def observe(self, snapshot):
        if self.fail:
            raise RuntimeError("secret failure")
        self.received = snapshot
        snapshot["nested"]["value"] = "shadow-mutated"
        return _ShadowOutput(
            legacy_summary={"intent_signature": "intent-hash"},
            planner_result={
                "hash_valid": True,
                "plan_signature": "plan-hash",
                "step_ids": ("step-1",),
                "tool_ids": ("app.discovery",),
            },
            discovery_result={
                "status": "RESOLVED",
                "application_signature": "app-hash",
                "launch_type": "aumid",
            },
            policy_result={"decision": "ALLOW"},
            authorization_result={"status": "VALIDATED_SIMULATION"},
        )


def _legacy_comparison(**overrides):
    values = {
        "intent_signature": "intent-hash",
        "plan_signature": "plan-hash",
        "step_ids": ("step-1",),
        "tool_ids": ("app.discovery",),
        "policy_decision": "ALLOW",
        "application_signature": "app-hash",
        "launch_type": "aumid",
        "authorization_state": "VALIDATED_SIMULATION",
    }
    values.update(overrides)
    return values


def test_controlled_pipeline_complete_shadow():
    shadow = _ShadowPipeline()
    diagnostics = ControlledRuntimeDiagnostics()
    pipeline = ControlledRuntimePipeline(
        control=RuntimeV2Control(
            routing_enabled=True,
            comparison_enabled=True,
        ),
        shadow_pipeline=shadow,
        diagnostics=diagnostics,
    )
    original = {"nested": {"value": "legacy"}}
    result = pipeline.observe(
        original,
        legacy_status="COMPLETED",
        legacy_comparison=_legacy_comparison(),
    )
    assert original == {"nested": {"value": "legacy"}}
    assert shadow.received is not original
    assert result.shadow_status == "OBSERVED"
    assert result.differences == ()
    assert result.authority is False
    snapshot = diagnostics.snapshot()
    assert snapshot.processed_events == 1
    assert snapshot.matches == 1


def test_controlled_pipeline_isolates_v2_errors():
    result = ControlledRuntimePipeline(
        control=RuntimeV2Control(
            routing_enabled=True,
            comparison_enabled=True,
        ),
        shadow_pipeline=_ShadowPipeline(fail=True),
    ).observe(
        {"legacy": "unchanged"},
        legacy_status="COMPLETED",
        legacy_comparison=_legacy_comparison(),
    )
    assert result.shadow_status == "ERROR"
    assert result.authority is False
    assert "shadow_pipeline_failure" in result.errors
    assert "secret failure" not in result.model_dump_json()


def test_controlled_pipeline_detects_comparison_divergence():
    result = ControlledRuntimePipeline(
        control=RuntimeV2Control(
            routing_enabled=True,
            comparison_enabled=True,
        ),
        shadow_pipeline=_ShadowPipeline(),
    ).observe(
        {"nested": {"value": "legacy"}},
        legacy_status="COMPLETED",
        legacy_comparison=_legacy_comparison(policy_decision="DENY"),
    )
    assert result.differences == (
        "POLICY_DIVERGENCE",
        "policy_decision_difference",
    )
    assert result.authority is False


def test_disabled_pipeline_does_not_load_or_call_shadow():
    shadow = _ShadowPipeline()
    result = ControlledRuntimePipeline(
        control=RuntimeV2Control(),
        shadow_pipeline=shadow,
    ).observe(
        {"prompt": "private prompt"},
        legacy_status="COMPLETED",
    )
    assert shadow.received is None
    assert result.shadow_status == "DISABLED"
    assert "private prompt" not in result.model_dump_json()
