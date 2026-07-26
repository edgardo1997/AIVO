"""Feature flag for isolated cutover evidence validation."""

import os


CUTOVER_VALIDATION_ENABLED = False
_CUTOVER_VALIDATION_ENV = "CUTOVER_VALIDATION_ENABLED"


def cutover_validation_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    if _CUTOVER_VALIDATION_ENV not in source:
        return CUTOVER_VALIDATION_ENABLED
    return source[_CUTOVER_VALIDATION_ENV].strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
