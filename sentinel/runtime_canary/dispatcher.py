"""Explicit dispatcher for already-captured legacy runtime events."""

from dataclasses import dataclass

from sentinel.shadow import CapturedRuntimeEvent

from .diagnostics import RuntimeCanaryInput, RuntimeCanaryResult


@dataclass(frozen=True)
class RuntimeCanaryDispatch:
    event_name: str
    result: RuntimeCanaryResult


class RuntimeCanaryDispatcher:
    """Forward observation events only when the pipeline is enabled."""

    _SUPPORTED = {
        "intent_received",
        "plan_created",
        "policy_evaluated",
        "consent_requested",
        "tool_requested",
        "execution_completed",
        "execution_failed",
    }

    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline

    def dispatch(
        self,
        event: CapturedRuntimeEvent,
        snapshot: RuntimeCanaryInput,
    ) -> RuntimeCanaryDispatch:
        if event.event_name not in self._SUPPORTED:
            raise ValueError("unsupported runtime canary event")
        return RuntimeCanaryDispatch(
            event_name=event.event_name,
            result=self._pipeline.observe(snapshot),
        )
