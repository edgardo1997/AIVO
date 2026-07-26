"""Component-hash comparison for deterministic replay validation."""

from dataclasses import dataclass
from enum import Enum


class ReplayComparisonStatus(str, Enum):
    MATCH = "MATCH"
    NON_DETERMINISTIC = "NON_DETERMINISTIC"
    REGRESSION = "REGRESSION"
    POLICY_CHANGE = "POLICY_CHANGE"
    PLAN_CHANGE = "PLAN_CHANGE"
    DISCOVERY_CHANGE = "DISCOVERY_CHANGE"
    AUTHORIZATION_CHANGE = "AUTHORIZATION_CHANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReplayComponentSignature:
    intent_hash: str
    plan_hash: str
    policy_decision_hash: str
    discovery_metadata_hash: str
    authorization_metadata_hash: str


def compare_signatures(
    expected: ReplayComponentSignature | None,
    actual: ReplayComponentSignature | None,
    *,
    repeated_execution: bool,
) -> ReplayComparisonStatus:
    if expected is None or actual is None:
        return ReplayComparisonStatus.UNKNOWN
    if expected == actual:
        return ReplayComparisonStatus.MATCH
    if repeated_execution:
        return ReplayComparisonStatus.NON_DETERMINISTIC
    differences = []
    if expected.intent_hash != actual.intent_hash:
        differences.append("intent")
    if expected.plan_hash != actual.plan_hash:
        differences.append("plan")
    if expected.policy_decision_hash != actual.policy_decision_hash:
        differences.append("policy")
    if expected.discovery_metadata_hash != actual.discovery_metadata_hash:
        differences.append("discovery")
    if expected.authorization_metadata_hash != actual.authorization_metadata_hash:
        differences.append("authorization")
    if len(differences) != 1:
        return ReplayComparisonStatus.REGRESSION
    return {
        "plan": ReplayComparisonStatus.PLAN_CHANGE,
        "policy": ReplayComparisonStatus.POLICY_CHANGE,
        "discovery": ReplayComparisonStatus.DISCOVERY_CHANGE,
        "authorization": ReplayComparisonStatus.AUTHORIZATION_CHANGE,
        "intent": ReplayComparisonStatus.REGRESSION,
    }[differences[0]]
