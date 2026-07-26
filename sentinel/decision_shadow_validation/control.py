"""Disabled-by-default control for decision shadow validation."""

import os

DECISION_SHADOW_VALIDATION_ENABLED = False
_ENV_NAME = "DECISION_SHADOW_VALIDATION_ENABLED"


class DecisionShadowValidationControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            DECISION_SHADOW_VALIDATION_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
