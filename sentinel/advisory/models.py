from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional


class InterventionLevel(IntEnum):
    NONE = 0
    SUGGESTION = 1
    WARNING = 2
    CRITICAL = 3


@dataclass(frozen=True)
class AdvisoryAction:
    id: str
    label: str
    delegated_intent: Optional[str] = None
    local_action: Optional[str] = None


@dataclass(frozen=True)
class AdvisoryInsight:
    kind: str
    title: str
    detail: str
    level: InterventionLevel


@dataclass(frozen=True)
class AdvisoryReport:
    confidence_score: float
    confidence_label: str
    explanation: str
    positive_factors: List[str] = field(default_factory=list)
    negative_factors: List[str] = field(default_factory=list)
    insights: List[AdvisoryInsight] = field(default_factory=list)
    intervention_level: InterventionLevel = InterventionLevel.NONE
    should_notify: bool = False
    actions: List[AdvisoryAction] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["intervention_level"] = int(self.intervention_level)
        for insight in result["insights"]:
            insight["level"] = int(insight["level"])
        return result
