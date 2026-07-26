"""Opt-in control for real-event shadow observation."""

SHADOW_RUNTIME_REAL_ENABLED = False


class ShadowRuntimeRealControl:
    def __init__(
        self,
        *,
        enabled: bool = SHADOW_RUNTIME_REAL_ENABLED,
    ) -> None:
        self.enabled = bool(enabled)
