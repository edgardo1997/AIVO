"""Feature flag for the isolated authorization canary."""

import os


AUTHORIZATION_CANARY_ENABLED = "AUTHORIZATION_CANARY_ENABLED"


def authorization_canary_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    return source.get(
        AUTHORIZATION_CANARY_ENABLED,
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
