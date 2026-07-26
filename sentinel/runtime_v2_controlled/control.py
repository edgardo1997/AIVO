"""Feature flags and non-executing activation states."""

import os
from dataclasses import dataclass
from enum import Enum


RUNTIME_V2_ROUTING_ENABLED = False
V2_COMPARISON_ENABLED = False
V2_DIAGNOSTIC_MODE = False


class RuntimeV2ActivationState(str, Enum):
    DISABLED = "DISABLED"
    SHADOW_ONLY = "SHADOW_ONLY"
    COMPARISON_ENABLED = "COMPARISON_ENABLED"


def _flag(
    name: str,
    default: bool,
    environ: dict[str, str],
) -> bool:
    if name not in environ:
        return default
    return environ[name].strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RuntimeV2Control:
    routing_enabled: bool = RUNTIME_V2_ROUTING_ENABLED
    comparison_enabled: bool = V2_COMPARISON_ENABLED
    diagnostic_mode: bool = V2_DIAGNOSTIC_MODE

    @classmethod
    def from_environment(
        cls,
        environ: dict[str, str] | None = None,
    ) -> "RuntimeV2Control":
        source = dict(os.environ if environ is None else environ)
        return cls(
            routing_enabled=_flag(
                "RUNTIME_V2_ROUTING_ENABLED",
                RUNTIME_V2_ROUTING_ENABLED,
                source,
            ),
            comparison_enabled=_flag(
                "V2_COMPARISON_ENABLED",
                V2_COMPARISON_ENABLED,
                source,
            ),
            diagnostic_mode=_flag(
                "V2_DIAGNOSTIC_MODE",
                V2_DIAGNOSTIC_MODE,
                source,
            ),
        )

    @property
    def state(self) -> RuntimeV2ActivationState:
        if not self.routing_enabled:
            return RuntimeV2ActivationState.DISABLED
        if self.comparison_enabled:
            return RuntimeV2ActivationState.COMPARISON_ENABLED
        return RuntimeV2ActivationState.SHADOW_ONLY
