"""Opt-in legacy-to-versioned contract adapters.

The existing Sentinel runtime does not import or register this package.
"""

from .app_adapter import app_profile_to_v1
from .intent_adapter import intent_to_v2
from .plan_adapter import plan_to_v2
from .pending_consent_adapter import pending_action_to_v1
from .policy_adapter import policy_result_to_v2

__all__ = [
    "app_profile_to_v1",
    "intent_to_v2",
    "plan_to_v2",
    "pending_action_to_v1",
    "policy_result_to_v2",
]
