"""Tests for PolicyContextV1 and PolicyDecisionV2 plan binding."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinel.adapters import policy_result_to_v2
from sentinel.contracts import (
    PolicyContextV1,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
)
from sentinel.core.policy import PolicyEffect, PolicyResult


def _context(**overrides) -> PolicyContextV1:
    user_id = overrides.pop("user_id", "user_local")
    values = {
        "schema_version": "1.0",
        "user_id": user_id,
        "identity_hash": PolicyContextV1.calculate_identity_hash(user_id),
        "plan_id": "plan_notepad",
        "intent_id": "intent_notepad",
        "risk_level": "medium",
        "evaluated_policies": ("identity", "application.launch"),
        "evaluated_policy_versions": {
            "identity": "1.0.0",
            "application.launch": "2.1.0",
        },
        "evaluated_at": datetime.now(timezone.utc),
        "policy_engine_version": "2.0.0-shadow",
        "decision_origin": "shadow-policy-adapter",
    }
    values.update(overrides)
    return PolicyContextV1.model_validate(values)


def _decision(context: PolicyContextV1) -> PolicyDecisionV2:
    return PolicyDecisionV2(
        schema_version="2.0",
        decision_id="decision_notepad",
        plan_id=context.plan_id,
        decision=PolicyDecisionValueV2.ALLOW,
        policy_ids=context.evaluated_policies,
        reason="All policies allowed",
        risk_context={"level": context.risk_level},
        timestamp=context.evaluated_at + timedelta(milliseconds=1),
        policy_context=context,
    )


def test_policy_context_requires_plan_id():
    payload = _context().model_dump()
    payload.pop("plan_id")

    with pytest.raises(ValidationError, match="Field required"):
        PolicyContextV1.model_validate(payload)


def test_policy_context_requires_consistent_identity():
    payload = _context().model_dump()
    payload["identity_hash"] = "f" * 64

    with pytest.raises(ValidationError, match="does not match user_id"):
        PolicyContextV1.model_validate(payload)


def test_policy_context_requires_versions_for_all_policies():
    payload = _context().model_dump()
    payload["evaluated_policy_versions"].pop("application.launch")

    with pytest.raises(
        ValidationError,
        match="must contain exactly every evaluated policy",
    ):
        PolicyContextV1.model_validate(payload)


def test_policy_decision_binds_context_to_same_plan():
    context = _context()
    decision = _decision(context)

    assert decision.plan_id == decision.policy_context.plan_id
    assert decision.policy_context.evaluated_policy_versions["application.launch"] == "2.1.0"

    payload = decision.model_dump()
    payload["plan_id"] = "different_plan"
    with pytest.raises(ValidationError, match="must match decision plan_id"):
        PolicyDecisionV2.model_validate(payload)


def test_policy_adapter_can_attach_policy_context_without_evaluation():
    context = _context()
    legacy = PolicyResult(
        effect=PolicyEffect.ALLOW,
        policy_id="identity,application.launch",
        reason="Allowed",
        context={"level": "medium"},
    )

    decision = policy_result_to_v2(
        legacy,
        plan_id=context.plan_id,
        timestamp=context.evaluated_at + timedelta(milliseconds=1),
        policy_context=context,
    )

    assert decision.policy_context == context
    assert decision.decision is PolicyDecisionValueV2.ALLOW
