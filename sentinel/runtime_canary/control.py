"""Feature control for the isolated runtime canary."""

import os


RUNTIME_CANARY_ENABLED = False
_RUNTIME_CANARY_ENV = "RUNTIME_CANARY_ENABLED"


def runtime_canary_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    if _RUNTIME_CANARY_ENV not in source:
        return RUNTIME_CANARY_ENABLED
    return source[_RUNTIME_CANARY_ENV].strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
