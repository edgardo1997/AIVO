"""Feature control for isolated stability validation."""

import os


STABILITY_VALIDATION_ENABLED = False
_STABILITY_VALIDATION_ENV = "STABILITY_VALIDATION_ENABLED"


def stability_validation_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    if _STABILITY_VALIDATION_ENV not in source:
        return STABILITY_VALIDATION_ENABLED
    return source[_STABILITY_VALIDATION_ENV].strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
