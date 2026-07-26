"""Feature flag for the isolated V2 policy observer."""

import os


POLICY_ENGINE_V2_SHADOW_ENABLED = "POLICY_ENGINE_V2_SHADOW_ENABLED"


def policy_shadow_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    return source.get(
        POLICY_ENGINE_V2_SHADOW_ENABLED,
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
