"""Pure adapter from the legacy Intent dataclass to IntentV2."""

from copy import deepcopy

from sentinel.contracts import IntentV2
from sentinel.core.intent import Intent

from ._ids import generated_id


def intent_to_v2(
    intent: Intent,
    *,
    intent_id: str | None = None,
) -> IntentV2:
    """Convert a legacy Intent without modifying or sharing mutable payloads."""
    if not isinstance(intent, Intent):
        raise TypeError("intent must be a sentinel.core.intent.Intent")

    return IntentV2(
        schema_version="2.0",
        intent_id=intent_id or generated_id("intent"),
        action=intent.action,
        target=intent.target,
        parameters=deepcopy(intent.parameters),
        confidence=intent.confidence,
        raw_input=intent.raw_input,
        grounding_requirements=tuple(deepcopy(intent.grounding_requirements)),
    )
