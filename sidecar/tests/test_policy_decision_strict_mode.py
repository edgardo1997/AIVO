from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    PolicyContextV1,
    PolicyDecisionV2Strict,
)


def _context(**changes):
    user_id = "user_local"
    data = {
        "schema_version": "1.0",
        "user_id": user_id,
        "identity_hash": PolicyContextV1.calculate_identity_hash(user_id),
        "plan_id": "plan_x",
        "intent_id": "intent_x",
        "risk_level": "medium",
        "evaluated_policies": ("identity", "application.launch"),
        "evaluated_policy_versions": {
            "identity": "1.0",
            "application.launch": "2.0",
        },
        "evaluated_at": datetime.now(timezone.utc),
        "policy_engine_version": "2.0-shadow",
        "decision_origin": "shadow-policy",
    }
    data.update(changes)
    return PolicyContextV1.model_validate(data)


def _payload(context):
    return {
        "schema_version": "2.0",
        "decision_id": "decision_x",
        "plan_id": context.plan_id,
        "intent_id": context.intent_id,
        "decision_origin": context.decision_origin,
        "decision": "ALLOW",
        "policy_ids": context.evaluated_policies,
        "reason": "Allowed",
        "risk_context": {"level": "medium"},
        "timestamp": context.evaluated_at + timedelta(milliseconds=1),
        "policy_context": context,
    }


def test_strict_decision_without_context_fails():
    payload = _payload(_context())
    payload.pop("policy_context")
    with pytest.raises(ValidationError, match="Field required"):
        PolicyDecisionV2Strict.model_validate(payload)


def test_strict_decision_wrong_plan_fails():
    payload = _payload(_context())
    payload["plan_id"] = "wrong"
    with pytest.raises(ValidationError, match="must match decision plan_id"):
        PolicyDecisionV2Strict.model_validate(payload)


def test_strict_decision_without_origin_fails():
    payload = _payload(_context())
    payload.pop("decision_origin")
    with pytest.raises(ValidationError, match="Field required"):
        PolicyDecisionV2Strict.model_validate(payload)


def test_strict_decision_without_policy_versions_fails():
    context = _context()
    payload = context.model_dump()
    payload["evaluated_policy_versions"] = {"identity": "1.0"}
    with pytest.raises(ValidationError, match="exactly every"):
        PolicyContextV1.model_validate(payload)
