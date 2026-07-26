"""Disabled-by-default feature control."""

import os

DECISION_LONG_TERM_ENABLED = False
_ENV_NAME = "DECISION_LONG_TERM_ENABLED"


class DecisionLongTermControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            DECISION_LONG_TERM_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
