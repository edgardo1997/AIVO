from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import logging
import time

from sentinel.testing.assertions import E2EAssertions

logger = logging.getLogger(__name__)


@dataclass
class E2EResult:
    scenario_name: str
    passed: bool
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 1),
            "details": self.details,
            "errors": self.errors,
        }


class E2ERunner:
    def __init__(self, runtime: Any, scenario_loader: Any = None):
        self._runtime = runtime
        self._scenario_loader = scenario_loader
        self._results: List[E2EResult] = []
        self._hooks: Dict[str, List[Callable]] = {
            "before_scenario": [],
            "after_scenario": [],
            "before_assert": [],
            "after_assert": [],
        }

    def on(self, event: str, fn: Callable) -> None:
        if event in self._hooks:
            self._hooks[event].append(fn)

    def _fire(self, event: str, **kwargs) -> None:
        for fn in self._hooks.get(event, []):
            try:
                fn(**kwargs)
            except Exception:
                logger.warning("E2E hook failed for event '%s'", event, exc_info=True)

    async def run_scenario(self, name: str, input_text: str, assertions: List[Callable[[Dict[str, Any]], None]]) -> E2EResult:
        self._fire("before_scenario", name=name, input_text=input_text)
        start = time.monotonic()
        errors: List[str] = []
        details: Dict[str, Any] = {}

        from sentinel.core.runtime import SentinelRequest

        request = SentinelRequest(utterance=input_text, session_id="e2e-test", user_id="test")
        try:
            response = await self._runtime.process(request)
            duration = (time.monotonic() - start) * 1000
            details["response"] = response.to_dict() if hasattr(response, "to_dict") else str(response)
            details["duration_ms"] = round(duration, 1)

            for assert_fn in assertions:
                self._fire("before_assert", name=name)
                try:
                    assert_fn(details.get("response", {}))
                except AssertionError as e:
                    errors.append(str(e))
                finally:
                    self._fire("after_assert", name=name)

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            errors.append(f"Runtime error: {e}")

        passed = len(errors) == 0
        result = E2EResult(
            scenario_name=name,
            passed=passed,
            duration_ms=round((time.monotonic() - start) * 1000, 1),
            details=details,
            errors=errors,
        )
        self._results.append(result)
        self._fire("after_scenario", name=name, result=result)
        return result

    async def run_all(self, scenarios: List[Any]) -> List[E2EResult]:
        self._results.clear()
        for scenario in scenarios:
            name = scenario.name if hasattr(scenario, "name") else scenario.get("name", "unnamed")
            input_text = scenario.input_text if hasattr(scenario, "input_text") else scenario.get("input", {}).get("text", "")
            assertions = []

            expected = scenario.expected if hasattr(scenario, "expected") else scenario.get("expected", {})
            if expected.get("success") is not False:
                assertions.append(lambda r: E2EAssertions.assert_success(r))
            if expected.get("intent"):
                cat = expected["intent"].get("type", "")
                if cat:
                    assertions.append(lambda r, c=cat: E2EAssertions.assert_intent_detected(r, c))
            if expected.get("security", {}).get("policy_checked"):
                assertions.append(lambda r: E2EAssertions.assert_decision_allowed(r))
            if expected.get("execution", {}).get("tool_called"):
                assertions.append(lambda r: E2EAssertions.assert_plan_has_steps(r))
            if expected.get("audit", {}).get("created"):
                assertions.append(lambda r: E2EAssertions.assert_audit_created(r))

            await self.run_scenario(name, input_text, assertions)
        return list(self._results)

    @property
    def results(self) -> List[E2EResult]:
        return list(self._results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self._results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self._results if not r.passed)

    @property
    def total(self) -> int:
        return len(self._results)

    def summary(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "success_rate": f"{self.passed / max(self.total, 1) * 100:.1f}%",
            "avg_duration_ms": round(sum(r.duration_ms for r in self._results) / max(self.total, 1), 1),
        }
