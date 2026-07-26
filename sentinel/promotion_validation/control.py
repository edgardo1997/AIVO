"""Feature control for promotion validation."""

import os


PROMOTION_VALIDATION_ENABLED = False
_PROMOTION_VALIDATION_ENV = "PROMOTION_VALIDATION_ENABLED"


def promotion_validation_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    if _PROMOTION_VALIDATION_ENV not in source:
        return PROMOTION_VALIDATION_ENABLED
    return source[_PROMOTION_VALIDATION_ENV].strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
