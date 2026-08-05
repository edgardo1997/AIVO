"""Fake provider adapters for canonical routing tests."""

from typing import Any, Dict, Iterator, List

from sentinel.core.router_types import ProviderSpec, RouterDecision


class FakeProviderAdapter:
    def __init__(self, results: Dict[str, Any]):
        self.results = results

    def execute_inference(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return self.results.get(decision.provider_id, {"response": "ok", "provider": decision.provider_id, "model": decision.model, "usage": None})

    def execute_inference_stream(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        yield {"response": "ok"}
