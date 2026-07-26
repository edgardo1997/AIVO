"""Opt-in control for the passive unified pipeline."""

V2_UNIFIED_PIPELINE_ENABLED = False


class UnifiedPipelineControl:
    """Explicit local control; no environment or runtime side effects."""

    def __init__(
        self,
        *,
        enabled: bool = V2_UNIFIED_PIPELINE_ENABLED,
    ) -> None:
        self.enabled = bool(enabled)
