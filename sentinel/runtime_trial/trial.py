"""Controlled V2 contract processing with simulated final outcome."""

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator

from sentinel.canary_environment.environment import (
    CanaryEnvironmentState,
    CanaryEnvironmentV1,
)
from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import require_timezone
from sentinel.contracts.execution_plan_v2 import ExecutionPlanV2, ExecutionStepV2
from sentinel.contracts.intent_v2 import IntentV2

from .comparison import RuntimeTrialComparison, RuntimeTrialComparisonStatus
from .control import RuntimeTrialControl
from .executor import SimulatedExecutor, SimulatedResult
from .metrics import RuntimeTrialMetrics
from .scenario import SanitizedScenarioV1


class RuntimeTrialStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class RuntimeTrialV1(DecisionResultV1):
    trial_id: str
    environment_id: str
    scenario_id: str
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    status: RuntimeTrialStatus


class RuntimeTrialResult(DecisionResultV1):
    trial: RuntimeTrialV1
    stage_states: tuple[str, ...]
    intent_hash: str
    plan_hash: str
    discovery_hash: str
    policy_hash: str
    authorization_hash: str
    policy_decision: str
    simulated_result: SimulatedResult
    comparison: RuntimeTrialComparisonStatus
    conversions: int
    latency_ms: float


class RuntimeTrialRunner:
    def __init__(
        self,
        *,
        control: RuntimeTrialControl,
        simulated_executor: SimulatedExecutor | None = None,
        metrics: RuntimeTrialMetrics | None = None,
    ) -> None:
        self.control = control
        self.simulator = simulated_executor or SimulatedExecutor()
        self.metrics = metrics or RuntimeTrialMetrics()

    def run_scenario(
        self,
        *,
        environment: CanaryEnvironmentV1,
        scenario: SanitizedScenarioV1,
        expected: dict[str, str] | None = None,
        simulated_success: bool = True,
    ) -> RuntimeTrialResult | None:
        if (
            not self.control.enabled
            or environment.authority is not False
            or environment.state is not CanaryEnvironmentState.RUNNING
        ):
            return None
        started = time.perf_counter()
        trial_id = f"trial_{uuid.uuid4().hex}"
        intent = IntentV2(
            schema_version="2.0",
            intent_id=f"intent_{scenario.scenario_hash[:20]}",
            action="simulate",
            target=f"scenario.{scenario.kind.value.lower()}",
            parameters={},
            confidence=1.0,
            raw_input=scenario.scenario_id,
        )
        step = ExecutionStepV2(
            schema_version="2.0",
            step_id=f"step_{scenario.scenario_hash[:20]}",
            tool_id="canary.simulation",
            parameters={},
            description="sanitized controlled trial",
        )
        plan = ExecutionPlanV2(
            schema_version="2.0",
            plan_id=f"plan_{scenario.scenario_hash[:20]}",
            intent_id=intent.intent_id,
            steps=(step,),
            params_hash=ExecutionPlanV2.calculate_params_hash(
                intent_id=intent.intent_id,
                steps=(step,),
            ),
        )
        signatures = {
            "intent_hash": _digest(intent.model_dump(mode="json")),
            "plan_hash": plan.params_hash,
            "discovery_hash": _digest({"scenario": scenario.scenario_hash, "evidence": "simulated"}),
            "policy_hash": _digest({"decision": "ALLOW_SIMULATION", "authority": False}),
            "authorization_hash": _digest({"state": "CANARY_VALIDATED", "authority": False}),
        }
        comparison = RuntimeTrialComparison.compare(signatures, expected)
        try:
            simulated_result = self.simulator.simulate(should_succeed=simulated_success)
        except Exception:
            simulated_result = SimulatedResult.SIMULATED_FAILURE
        succeeded = simulated_result is SimulatedResult.SIMULATED_SUCCESS
        elapsed = (time.perf_counter() - started) * 1000
        trial = RuntimeTrialV1(
            trial_id=trial_id,
            environment_id=environment.environment_id,
            scenario_id=scenario.scenario_id,
            timestamp=datetime.now(timezone.utc),
            status=(RuntimeTrialStatus.COMPLETED if succeeded else RuntimeTrialStatus.FAILED),
        )
        result = RuntimeTrialResult(
            trial=trial,
            stage_states=(
                "INTENT_V2_CREATED",
                "PLAN_V2_CREATED",
                "DISCOVERY_V2_SIMULATED",
                "POLICY_V2_SHADOW_EVALUATED",
                "AUTHORIZATION_CANARY_VALIDATED",
            ),
            **signatures,
            policy_decision="ALLOW_SIMULATION",
            simulated_result=simulated_result,
            comparison=comparison,
            conversions=5,
            latency_ms=elapsed,
        )
        self.metrics.record(
            succeeded=succeeded,
            comparison=comparison,
            latency_ms=elapsed,
            conversions=5,
        )
        return result


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
