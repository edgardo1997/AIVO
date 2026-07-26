"""Isolated human-consent recording for Sentinel V2."""

from .consent import ConsentManagerV2
from .control import CONSENT_MANAGER_V2_ENABLED, ConsentManagerControl
from .revocation import ConsentRevocationRecordV1

__all__ = [
    "CONSENT_MANAGER_V2_ENABLED",
    "ConsentManagerControl",
    "ConsentManagerV2",
    "ConsentRevocationRecordV1",
]
