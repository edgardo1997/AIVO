"""Disabled-by-default final readiness control."""

import os

FINAL_CONTROL_PLANE_READINESS_ENABLED = False
_ENV_NAME = "FINAL_CONTROL_PLANE_READINESS_ENABLED"


class FinalControlPlaneControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            FINAL_CONTROL_PLANE_READINESS_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
