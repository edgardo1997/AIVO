"""Pipeline profiles define which intelligence stages run for each class of request.

This is not a mandatory 17-stage runtime. Each profile is a declarative contract
used by the coordinator to choose the minimum safe set of stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class PipelineProfileDefinition:
    name: str
    required_stages: List[str] = field(default_factory=list)
    forbidden_stages: List[str] = field(default_factory=list)
    target_latency: str = "adaptive"
    can_execute_tools: bool = False
    can_learn: bool = False


FAST_CONVERSATION = PipelineProfileDefinition(
    name="fast_conversation",
    required_stages=[
        "identity",
        "language",
        "input_understanding",
        "intent",
        "context_selection",
        "provider_routing",
        "response_validation",
        "persistence",
    ],
    forbidden_stages=[
        "planning",
        "risk_evaluation",
        "governance",
        "execution",
        "verification",
        "explanation",
    ],
    target_latency="low",
    can_execute_tools=False,
    can_learn=False,
)


GOVERNED_ACTION = PipelineProfileDefinition(
    name="governed_action",
    required_stages=[
        "identity",
        "language",
        "input_understanding",
        "intent",
        "ambiguity",
        "context_selection",
        "memory_selection",
        "world_model",
        "planning",
        "risk_evaluation",
        "governance",
        "execution",
        "verification",
        "explanation",
        "persistence",
    ],
    forbidden_stages=[],
    target_latency="adaptive",
    can_execute_tools=True,
    can_learn=False,
)


POST_EXECUTION_LEARNING = PipelineProfileDefinition(
    name="post_execution_learning",
    required_stages=[
        "identity",
        "verification",
        "learning",
        "persistence",
    ],
    forbidden_stages=[
        "language",
        "input_understanding",
        "intent",
        "planning",
        "governance",
        "execution",
    ],
    target_latency="background",
    can_execute_tools=False,
    can_learn=True,
)


BACKGROUND_MAINTENANCE = PipelineProfileDefinition(
    name="background_maintenance",
    required_stages=[
        "world_model",
        "memory",
        "learning",
        "persistence",
    ],
    forbidden_stages=[
        "language",
        "input_understanding",
        "intent",
        "planning",
        "risk_evaluation",
        "governance",
        "execution",
    ],
    target_latency="background",
    can_execute_tools=False,
    can_learn=False,
)


PROFILES = {
    "fast_conversation": FAST_CONVERSATION,
    "governed_action": GOVERNED_ACTION,
    "post_execution_learning": POST_EXECUTION_LEARNING,
    "background_maintenance": BACKGROUND_MAINTENANCE,
}


def select_profile(intent: str, is_executable: bool, ambiguity_action: str = "proceed") -> PipelineProfileDefinition:
    """Choose a profile without executing anything."""
    if is_executable and ambiguity_action in ("proceed", "auto_correct", "infer"):
        return GOVERNED_ACTION
    return FAST_CONVERSATION
