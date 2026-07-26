"""Versioned representation of normalized human intent.

IntentV2 preserves the original human utterance separately from the normalized
action, target, and structured parameters. It is not connected to IntentEngine.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from ._base import FROZEN_MODEL_CONFIG, NonEmptyString


class IntentV2(BaseModel):
    """Immutable transition contract for a normalized Sentinel intent."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["2.0"]
    intent_id: NonEmptyString
    action: NonEmptyString
    target: NonEmptyString
    parameters: dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    raw_input: NonEmptyString
    grounding_requirements: tuple[Any, ...] = ()
