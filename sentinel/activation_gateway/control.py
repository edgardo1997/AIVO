"""Disabled-by-default gateway controls."""

import os

ACTIVATION_GATEWAY_ENABLED = False
V2_ACTIVATION_ALLOWED = False
_GATEWAY_ENV = "ACTIVATION_GATEWAY_ENABLED"
_V2_ENV = "V2_ACTIVATION_ALLOWED"


class ActivationGatewayControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        v2_allowed: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        self.enabled = _resolve(
            enabled,
            source.get(_GATEWAY_ENV),
            ACTIVATION_GATEWAY_ENABLED,
        )
        self.v2_allowed = _resolve(
            v2_allowed,
            source.get(_V2_ENV),
            V2_ACTIVATION_ALLOWED,
        )


def _resolve(explicit: bool | None, raw: str | None, default: bool) -> bool:
    if explicit is not None:
        return explicit
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
