"""Canonical context window validation for routing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sentinel.core.model_schemas import CapabilityStatus


class ContextWindowValidator:
    """Validate a model candidate against a request's token budget."""

    SYSTEM_OVERHEAD = 64
    PROVIDER_OVERHEAD = 32

    def estimate_request_tokens(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        structured_output_schema: Optional[Dict[str, Any]] = None,
    ) -> int:
        total = self.SYSTEM_OVERHEAD + self.PROVIDER_OVERHEAD
        total += len(system_prompt.split())
        for m in messages:
            total += len(str(m.get("content", "")).split())
        if tool_schemas:
            for t in tool_schemas:
                total += len(str(t).split())
        if structured_output_schema:
            total += len(str(structured_output_schema).split())
        return total

    def candidate_fits(
        self,
        context_tokens: int,
        reserved_output_tokens: int,
        max_context: int,
        max_output: int,
        status: CapabilityStatus,
        critical: bool,
    ) -> bool:
        if status == CapabilityStatus.UNKNOWN and critical:
            return False
        if max_context == 0 or max_context == -1:
            return not critical
        return (context_tokens + reserved_output_tokens + self.PROVIDER_OVERHEAD) <= max_context
