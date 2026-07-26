import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.contracts import AuditEventV1

CONTRACTS_ROOT = Path(__file__).parents[2] / "sentinel" / "contracts"
NEW_MODULES = (
    "authority.py",
    "decision.py",
    "evidence.py",
    "health.py",
    "readiness.py",
    "audit.py",
)
FORBIDDEN_IMPORTS = {
    "executor",
    "tool_gateway",
    "orchestrator",
    "planner",
    "policy_engine",
    "decision_engine",
    "subprocess",
}


def test_core_contracts_do_not_import_productive_components():
    for filename in NEW_MODULES:
        tree = ast.parse((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not any(forbidden in imported for imported in imports for forbidden in FORBIDDEN_IMPORTS)


def test_audit_event_is_immutable_and_non_authoritative():
    event = AuditEventV1(
        event_id="audit-1",
        event_type="readiness_evaluated",
        timestamp=datetime.now(UTC),
        correlation_id="correlation-1",
        evidence_hash="audit-hash",
        issuer_id="issuer.audit.v1",
        result="BLOCKED",
    )

    assert event.authority is False
    assert event.execution_requested is False
    with pytest.raises(ValidationError):
        event.result = "AUTHORIZED"


@pytest.mark.parametrize("alias", ["action_requested", "authority_explicit"])
def test_audit_event_rejects_dangerous_aliases(alias):
    values = {
        "event_id": "audit-1",
        "event_type": "readiness_evaluated",
        "timestamp": datetime.now(UTC),
        "correlation_id": "correlation-1",
        "evidence_hash": "audit-hash",
        "issuer_id": "issuer.audit.v1",
        "result": "BLOCKED",
        alias: False,
    }

    with pytest.raises(ValidationError):
        AuditEventV1(**values)
