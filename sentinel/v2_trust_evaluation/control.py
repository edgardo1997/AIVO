"""Disabled-by-default trust evaluation control."""

import os

V2_TRUST_EVALUATION_ENABLED = False
_ENV_NAME = "V2_TRUST_EVALUATION_ENABLED"


class TrustEvaluationControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            V2_TRUST_EVALUATION_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
