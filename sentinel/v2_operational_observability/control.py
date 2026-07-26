"""Disabled-by-default operational observability control."""

import os

V2_OPERATIONAL_OBSERVABILITY_ENABLED = False
_ENV_NAME = "V2_OPERATIONAL_OBSERVABILITY_ENABLED"


class V2OperationalObservabilityControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            V2_OPERATIONAL_OBSERVABILITY_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
