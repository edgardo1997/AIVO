"""Disabled and zero-traffic defaults for controlled activation."""

import os

CONTROLLED_RUNTIME_ACTIVATION_ENABLED = False
V2_CANARY_ENABLED = False
V2_TRAFFIC_PERCENTAGE = 0
MAX_V2_TRAFFIC_PERCENTAGE = 5


class ControlledActivationControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        canary_enabled: bool | None = None,
        traffic_percentage: int | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        self.enabled = _flag(
            enabled,
            source.get("CONTROLLED_RUNTIME_ACTIVATION_ENABLED"),
            CONTROLLED_RUNTIME_ACTIVATION_ENABLED,
        )
        self.canary_enabled = _flag(
            canary_enabled,
            source.get("V2_CANARY_ENABLED"),
            V2_CANARY_ENABLED,
        )
        raw_percentage = source.get("V2_TRAFFIC_PERCENTAGE")
        percentage = (
            traffic_percentage
            if traffic_percentage is not None
            else int(raw_percentage)
            if raw_percentage is not None
            else V2_TRAFFIC_PERCENTAGE
        )
        if not 0 <= percentage <= MAX_V2_TRAFFIC_PERCENTAGE:
            raise ValueError("V2 traffic percentage must be between 0 and 5")
        self.traffic_percentage = percentage


def _flag(explicit: bool | None, raw: str | None, default: bool) -> bool:
    if explicit is not None:
        return explicit
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
