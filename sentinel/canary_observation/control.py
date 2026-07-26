"""Feature control for passive canary observation."""

import os


CANARY_OBSERVATION_ENABLED = False
_CANARY_OBSERVATION_ENV = "CANARY_OBSERVATION_ENABLED"


def canary_observation_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    if _CANARY_OBSERVATION_ENV not in source:
        return CANARY_OBSERVATION_ENABLED
    return source[_CANARY_OBSERVATION_ENV].strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
