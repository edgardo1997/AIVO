"""Immutable, explicitly non-authoritative gateway decision."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import require_timezone


class SelectedAuthority(str, Enum):
    LEGACY_ONLY = "LEGACY_ONLY"
    V2_NOT_AVAILABLE = "V2_NOT_AVAILABLE"
    V2_ELIGIBLE_SHADOW = "V2_ELIGIBLE_SHADOW"
    V2_ELIGIBLE_CANARY = "V2_ELIGIBLE_CANARY"
    BLOCKED = "BLOCKED"


class AuthoritySelectionDecisionV1(DecisionResultV1):
    decision_id: str
    selected_authority: SelectedAuthority
    reason_codes: tuple[str, ...]
    validation_summary: tuple[str, ...]
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
