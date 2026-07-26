from dataclasses import replace

import pytest

from sentinel.v2_authority_readiness import (
    AuthorityReadinessState,
    ReadinessEvidenceV1,
    V2AuthorityReadinessControl,
    V2AuthorityReadinessEngine,
)


def evidence() -> ReadinessEvidenceV1:
    return ReadinessEvidenceV1(
        True,
        True,
        0,
        1.0,
        0,
        0,
        True,
        True,
        False,
        True,
        5,
        0,
        10,
        0,
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identity_available", False),
        ("authorization_consistent", False),
        ("replay_detected", True),
        ("resolver_evidence_valid", False),
        ("direct_tool_execution", True),
        ("gateway_bypass", True),
        ("hidden_authority", True),
    ],
)
def test_security_or_boundary_failure_blocks(field, value) -> None:
    result = V2AuthorityReadinessEngine(control=V2AuthorityReadinessControl(enabled=True)).evaluate(
        replace(evidence(), **{field: value})
    )
    assert result.status is AuthorityReadinessState.BLOCKED
    assert result.authority is False


def test_evidence_contains_only_aggregates() -> None:
    fields = set(ReadinessEvidenceV1.__dataclass_fields__)
    assert fields.isdisjoint(
        {
            "user",
            "prompt",
            "command",
            "path",
            "arguments",
            "secrets",
            "parameters",
        }
    )
