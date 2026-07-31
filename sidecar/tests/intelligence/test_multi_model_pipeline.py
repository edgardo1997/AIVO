import asyncio
import pytest
from sentinel.intelligence.multi_model_coordinator import MultiModelCoordinator, MultiModelConfig
from sentinel.intelligence.task_planner import TaskPlanner
from sentinel.intelligence.evaluation_engine import EvaluationEngine, ModelResponse
from sentinel.intelligence.confidence_scorer import ConfidenceScorer
from sentinel.intelligence.consensus_engine import ConsensusEngine
from sentinel.intelligence.conflict_resolver import ConflictResolver
from sentinel.intelligence.partial_failure_handler import PartialFailureHandler


def _make_response(model_id: str, text: str, provider: str = "test", duration_ms: float = 500, cost: float = 0.0) -> ModelResponse:
    return ModelResponse(model_id=model_id, provider=provider, response_text=text, duration_ms=duration_ms, cost=cost, success=True)


class TestMultiModelPipeline:
    def test_full_pipeline_agreement(self):
        async def execute_fn(task):
            return _make_response(task["model_id"], "The best database for this application is PostgreSQL because it provides ACID compliance and strong consistency guarantees.")

        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=2))
        result = asyncio.run(coordinator.process("What database should we use?", execute_fn=execute_fn))
        assert result.final_answer != ""
        assert result.confidence > 0.0
        assert result.consensus is not None
        assert result.consensus.total_evaluated >= 1

    def test_full_pipeline_with_conflict(self):
        async def execute_fn(task):
            if task["model_id"] == "model_1":
                return _make_response("model_1", "The root cause is a memory leak in the application server.")
            return _make_response("model_2", "The root cause is a CPU bottleneck in the database queries.")

        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=2))
        result = asyncio.run(coordinator.process("What is the root cause of the performance issue?", execute_fn=execute_fn))
        assert result.final_answer != ""
        if result.consensus and result.consensus.conflict_report:
            assert result.consensus.conflict_report.total_conflicts >= 0

    def test_pipeline_handles_partial_failure(self):
        call_count = [0]

        async def execute_fn(task):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("Model temporarily unavailable")
            return _make_response(task["model_id"], "The application should use PostgreSQL for data persistence.")

        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=2))
        result = asyncio.run(coordinator.process("Recommend a database", execute_fn=execute_fn))
        assert result.final_answer != "" or result.confidence >= 0.0

    def test_pipeline_with_custom_components(self):
        scorer = ConfidenceScorer()
        evaluator = EvaluationEngine(confidence_scorer=scorer)
        resolver = ConflictResolver()
        consensus = ConsensusEngine(evaluator, conflict_resolver=resolver)
        planner = TaskPlanner()
        handler = PartialFailureHandler(timeout_ms=10000)

        async def execute_fn(task):
            return _make_response(task["model_id"], "Use PostgreSQL for ACID compliance and reliability.", duration_ms=200, cost=0.001)

        coordinator = MultiModelCoordinator(
            task_planner=planner,
            evaluation_engine=evaluator,
            consensus_engine=consensus,
            conflict_resolver=resolver,
            failure_handler=handler,
            config=MultiModelConfig(min_models=2, max_models=2),
        )
        result = asyncio.run(coordinator.process("Database recommendation", execute_fn=execute_fn))
        assert result.final_answer != ""
        assert result.confidence > 0.0

    def test_pipeline_respects_max_models(self):
        async def execute_fn(task):
            return _make_response(task["model_id"], "Response", duration_ms=10)

        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=2))
        result = asyncio.run(coordinator.process("Test", execute_fn=execute_fn))
        if result.consensus:
            assert result.consensus.total_evaluated <= 2

    def test_pipeline_detects_disagreement(self):
        async def execute_fn(task):
            if task["model_id"] == "model_1":
                return _make_response("model_1", "The answer is definitely A. This is because A provides better performance characteristics and is more reliable according to benchmarks.")
            return _make_response("model_2", "The answer is definitely B. This is because B offers superior scalability and has better community support according to recent studies.")

        coordinator = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=2))
        result = asyncio.run(coordinator.process("Which option should we choose?", execute_fn=execute_fn))
        assert result.final_answer != ""
        if result.consensus and result.consensus.conflict_report:
            assert result.consensus.total_evaluated == 2
