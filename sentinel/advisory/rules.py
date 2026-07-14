from typing import Any, Protocol, Sequence

from .confidence import ConfidenceAssessment
from .models import AdvisoryInsight


class AdvisoryRule(Protocol):
    """Extension point. Rules inspect outcomes and may only return insights."""

    def evaluate(self, result: Any, confidence: ConfidenceAssessment) -> Sequence[AdvisoryInsight]: ...
