"""Deep hash comparison without changing either decision."""

from dataclasses import dataclass
from enum import Enum

from .classification import DecisionClassification
from .decision_capture import LegacyDecisionSnapshot, V2DecisionSnapshot


class ComponentComparisonStatus(str, Enum):
    MATCH = "MATCH"
    DIFFERENT = "DIFFERENT"


@dataclass(frozen=True)
class ComponentComparison:
    intent: ComponentComparisonStatus
    plan: ComponentComparisonStatus
    policy: ComponentComparisonStatus
    discovery: ComponentComparisonStatus
    authorization: ComponentComparisonStatus


class DecisionComparison:
    @staticmethod
    def compare(
        legacy: LegacyDecisionSnapshot,
        v2: V2DecisionSnapshot,
    ) -> tuple[ComponentComparison, DecisionClassification]:
        components = ComponentComparison(
            intent=_status(legacy.intent_hash, v2.intent_hash),
            plan=_status(legacy.plan_hash, v2.plan_hash),
            policy=_status(legacy.policy_hash, v2.policy_hash),
            discovery=_status(legacy.discovery_hash, v2.discovery_hash),
            authorization=_status(
                legacy.authorization_hash,
                v2.authorization_hash,
            ),
        )
        values = tuple(components.__dict__.values())
        if all(value is ComponentComparisonStatus.MATCH for value in values):
            classification = DecisionClassification.EXPECTED_MATCH
        elif "SECURITY_IMPROVEMENT" in v2.codes:
            classification = DecisionClassification.SECURITY_IMPROVEMENT
        elif "LEGACY_KNOWN_GAP" in legacy.codes:
            classification = DecisionClassification.LEGACY_DIFFERENCE
        elif (
            components.policy is ComponentComparisonStatus.DIFFERENT
            or components.authorization is ComponentComparisonStatus.DIFFERENT
        ):
            classification = DecisionClassification.CRITICAL_DIVERGENCE
        else:
            classification = DecisionClassification.V2_DIFFERENCE
        return components, classification


def _status(left: str, right: str) -> ComponentComparisonStatus:
    return ComponentComparisonStatus.MATCH if left == right else ComponentComparisonStatus.DIFFERENT
