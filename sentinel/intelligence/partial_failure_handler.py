from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import asyncio
import time
import logging

from sentinel.intelligence.evaluation_engine import ModelResponse, EvaluatedResponse

logger = logging.getLogger(__name__)


@dataclass
class PartialFailureReport:
    total_models: int = 0
    successful: int = 0
    failed: int = 0
    timed_out: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)
    used_responses: List[str] = field(default_factory=list)
    degraded: bool = False
    recovery_strategy: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_models": self.total_models,
            "successful": self.successful,
            "failed": self.failed,
            "timed_out": self.timed_out,
            "failures": list(self.failures),
            "used_responses": list(self.used_responses),
            "degraded": self.degraded,
            "recovery_strategy": self.recovery_strategy,
        }


class PartialFailureHandler:
    def __init__(self, timeout_ms: float = 30000.0):
        self._timeout_ms = timeout_ms
        self._history: List[PartialFailureReport] = []

    async def execute_with_partial_handling(self, tasks: List[Dict[str, Any]], execute_fn, timeout: Optional[float] = None) -> Dict[str, Any]:
        effective_timeout = timeout or self._timeout_ms
        results: List[ModelResponse] = []
        failures: List[Dict[str, Any]] = []
        successful_ids: List[str] = []
        start = time.monotonic()
        for task in tasks:
            task_start = time.monotonic()
            remaining = effective_timeout - (time.monotonic() - start) * 1000
            if remaining <= 0:
                failures.append({"task_id": task.get("task_id", "unknown"), "error": "timeout_budget_exhausted", "duration_ms": (time.monotonic() - task_start) * 1000})
                continue
            try:
                result = await asyncio.wait_for(execute_fn(task), timeout=max(0.1, remaining / 1000))
                results.append(result)
                successful_ids.append(task.get("task_id", "unknown"))
            except asyncio.TimeoutError:
                failures.append({"task_id": task.get("task_id", "unknown"), "error": "timeout", "duration_ms": effective_timeout})
            except Exception as e:
                failures.append({"task_id": task.get("task_id", "unknown"), "error": str(e)[:200], "duration_ms": (time.monotonic() - task_start) * 1000})
        report = PartialFailureReport(
            total_models=len(tasks),
            successful=len(results),
            failed=len([f for f in failures if f["error"] != "timeout"]),
            timed_out=len([f for f in failures if f["error"] == "timeout"]),
            failures=failures,
            used_responses=successful_ids,
        )
        self._history.append(report)
        if report.failed > 0 or report.timed_out > 0:
            report.degraded = True
            if report.successful == 0:
                report.recovery_strategy = "all_failed"
                raise RuntimeError(f"All {len(tasks)} model(s) failed. Last error: {failures[-1]['error'] if failures else 'unknown'}")
            elif report.successful >= len(tasks) / 2:
                report.recovery_strategy = "majority_available"
            else:
                report.recovery_strategy = "minority_available"
                logger.warning("Partial failure: %d/%d models succeeded, continuing with degraded results", report.successful, len(tasks))
        else:
            report.recovery_strategy = "all_available"
        return {"results": results, "report": report}

    def get_history(self) -> List[PartialFailureReport]:
        return list(self._history)

    def get_recent_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        all_failures = []
        for report in self._history[-limit:]:
            all_failures.extend(report.failures)
        return all_failures[-limit:]
