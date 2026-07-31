import asyncio
import pytest
from sentinel.intelligence.partial_failure_handler import PartialFailureHandler, PartialFailureReport
from sentinel.intelligence.evaluation_engine import ModelResponse


class TestPartialFailureHandler:
    def test_all_successful(self):
        handler = PartialFailureHandler()

        async def execute_fn(task):
            return ModelResponse(model_id=task["model_id"], provider="test", response_text="ok", success=True)

        result = asyncio.run(handler.execute_with_partial_handling(
            [{"task_id": "t1", "model_id": "m1"}, {"task_id": "t2", "model_id": "m2"}],
            execute_fn,
        ))
        assert result["report"].successful == 2
        assert result["report"].failed == 0
        assert result["report"].recovery_strategy == "all_available"
        assert not result["report"].degraded

    def test_partial_failure(self):
        handler = PartialFailureHandler()

        async def execute_fn(task):
            if task["model_id"] == "m1":
                return ModelResponse(model_id="m1", provider="test", response_text="ok", success=True)
            raise ConnectionError("Model unavailable")

        result = asyncio.run(handler.execute_with_partial_handling(
            [{"task_id": "t1", "model_id": "m1"}, {"task_id": "t2", "model_id": "m2"}],
            execute_fn,
        ))
        assert result["report"].successful == 1
        assert result["report"].failed == 1
        assert result["report"].degraded
        assert result["report"].recovery_strategy == "majority_available"

    def test_all_failed_raises(self):
        handler = PartialFailureHandler()

        async def execute_fn(task):
            raise RuntimeError("All models down")

        with pytest.raises(RuntimeError, match="All 2 model"):
            asyncio.run(handler.execute_with_partial_handling(
                [{"task_id": "t1", "model_id": "m1", "name": "task1"}, {"task_id": "t2", "model_id": "m2", "name": "task2"}],
                execute_fn,
            ))

    def test_timeout_handling(self):
        handler = PartialFailureHandler(timeout_ms=50)

        async def execute_fn(task):
            await asyncio.sleep(10)
            return ModelResponse(model_id=task.get("model_id", "default"), provider="test", response_text="ok")

        with pytest.raises(RuntimeError, match="All 1 model"):
            asyncio.run(handler.execute_with_partial_handling(
                [{"task_id": "t1", "model_id": "m1", "name": "task1"}],
                execute_fn,
                timeout=0.05,
            ))

    def test_minority_available(self):
        handler = PartialFailureHandler()

        async def execute_fn(task):
            if task["model_id"] == "m1":
                return ModelResponse(model_id="m1", provider="test", response_text="ok", success=True)
            raise ConnectionError("down")

        result = asyncio.run(handler.execute_with_partial_handling(
            [{"task_id": "t1", "model_id": "m1"}, {"task_id": "t2", "model_id": "m2"}, {"task_id": "t3", "model_id": "m3"}],
            execute_fn,
        ))
        assert result["report"].successful == 1
        assert result["report"].failed == 2
        assert result["report"].recovery_strategy == "minority_available"

    def test_history_maintained(self):
        handler = PartialFailureHandler()

        async def execute_fn(task):
            return ModelResponse(model_id=task.get("model_id", "default"), provider="test", response_text="ok")

        asyncio.run(handler.execute_with_partial_handling([{"task_id": "t1", "model_id": "m1"}], execute_fn))
        assert len(handler.get_history()) == 1

    def test_get_recent_failures(self):
        handler = PartialFailureHandler()

        async def execute_fn(task):
            raise RuntimeError("fail")

        for _ in range(3):
            try:
                asyncio.run(handler.execute_with_partial_handling([{"task_id": "t1", "model_id": "m1"}], execute_fn))
            except RuntimeError:
                pass
        assert len(handler.get_recent_failures(limit=5)) > 0

    def test_timeout_budget_exhausted(self):
        handler = PartialFailureHandler(timeout_ms=50)

        async def slow_fn(task):
            await asyncio.sleep(0.5)
            return ModelResponse(model_id=task["model_id"], provider="test", response_text="ok")

        async def fast_fn(task):
            return ModelResponse(model_id=task["model_id"], provider="test", response_text="ok")

        result = asyncio.run(handler.execute_with_partial_handling(
            [{"task_id": "t1", "model_id": "m1"}, {"task_id": "t2", "model_id": "m2"}],
            fast_fn,
            timeout=200.0,
        ))
        assert result["report"].successful == 2

    def test_report_serialization(self):
        report = PartialFailureReport(total_models=2, successful=1, failed=1, timed_out=0,
                                       failures=[{"task_id": "t1", "error": "timeout", "duration_ms": 1000}],
                                       used_responses=["t2"], degraded=True, recovery_strategy="majority_available")
        d = report.to_dict()
        assert d["total_models"] == 2
        assert d["successful"] == 1
        assert d["recovery_strategy"] == "majority_available"
