"""Disabled-by-default Tool Gateway V2 control."""

import os

TOOL_GATEWAY_V2_ENABLED = False
_ENV_NAME = "TOOL_GATEWAY_V2_ENABLED"


class ToolGatewayControl:
    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            TOOL_GATEWAY_V2_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
