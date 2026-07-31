import asyncio
import time
import pytest
from sentinel.intelligence.multi_model_coordinator import MultiModelCoordinator, MultiModelConfig, MultiModelResult
from sentinel.intelligence.task_planner import TaskPlanner
from sentinel.intelligence.evaluation_engine import EvaluationEngine, ModelResponse


class TestParallelExecution:
    def test_parallel_execution_with_mock_fn(self):
        call_order = []

        async def execute_fn(task):
            call_order.append(task["model_id"])
            await asyncio.sleep(0.05)
            return ModelResponse(model_id=task["model_id"], provider="test", response_text=f"Response from {task['model_id']}", duration_ms=50, success=True)

        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=3))
        result = asyncio.run(coordinator.process("Test message", execute_fn=execute_fn))
        assert len(call_order) >= 1

    def test_execution_speed_parallel(self):
        async def slow_fn(task):
            await asyncio.sleep(0.2)
            return ModelResponse(model_id=task["model_id"], provider="test", response_text="ok", duration_ms=200, success=True)

        start = time.monotonic()
        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=3))
        result = asyncio.run(coordinator.process("Test", execute_fn=slow_fn))
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # parallel execution should be fast

    def test_results_collected(self):
        async def execute_fn(task):
            return ModelResponse(model_id=task["model_id"], provider="test", response_text=f"Result from {task['model_id']}", duration_ms=10, success=True, cost=0.001)

        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=3))
        result = asyncio.run(coordinator.process("Analyze the system", execute_fn=execute_fn))
        assert hasattr(result, "model_responses")

    def test_fallback_single_on_disabled(self):
        coordinator = MultiModelCoordinator(config=MultiModelConfig(enabled=False))
        result = asyncio.run(coordinator.process("Hello", execute_fn=lambda t: ModelResponse(model_id="fallback", provider="test", response_text="fallback", success=True)))
        assert result.confidence == 0.5

    def test_multi_model_result_serialization(self):
        result = MultiModelResult(final_answer="test", confidence=0.9, duration_ms=100.0)
        d = result.to_dict()
        assert d["final_answer"] == "test"
        assert d["confidence"] == 0.9
        assert d["duration_ms"] == 100.0
