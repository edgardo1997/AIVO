from sentinel.activation_gateway import (
    ActivationGatewayAudit,
    ActivationGatewayMetrics,
    GatewayFallback,
    SelectedAuthority,
)


def test_fallback_returns_legacy_without_execution() -> None:
    metrics = ActivationGatewayMetrics()
    audit = ActivationGatewayAudit()
    result = GatewayFallback(metrics=metrics, audit=audit).require_legacy()

    assert result.selected_authority is SelectedAuthority.LEGACY_ONLY
    assert result.authority is False
    assert result.execution_requested is False
    assert metrics.snapshot().fallbacks == 1
    assert audit.snapshot()[0].event_type == "fallback_required"
    assert not hasattr(result, "runtime")
    assert not hasattr(result, "tool")


def test_audit_accepts_only_allowed_events() -> None:
    audit = ActivationGatewayAudit()
    audit.record("legacy_selected", "LEGACY_ONLY")
    assert len(audit.snapshot()) == 1
    try:
        audit.record("prompt_recorded", "SHOULD_FAIL")
    except ValueError:
        pass
    assert len(audit.snapshot()) == 1
