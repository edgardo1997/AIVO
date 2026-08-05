"""Contract and classification for provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class AdapterClassification(str, Enum):
    SUPPORTED = "SUPPORTED"
    EXPERIMENTAL = "EXPERIMENTAL"
    DISABLED = "DISABLED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class AdapterContractResult:
    provider: str
    checks: Dict[str, bool] = field(default_factory=dict)
    external_validation: bool = False
    classification: AdapterClassification = AdapterClassification.UNSUPPORTED
    notes: List[str] = field(default_factory=list)

    def pass_rate(self) -> float:
        if not self.checks:
            return 0.0
        return sum(1 for v in self.checks.values() if v) / len(self.checks)
