from types import SimpleNamespace

from sentinel.advisory import AdvisoryConfig, AdvisoryService
from sentinel.core.orchestrator import Orchestrator


def _result(*, error=None, success=True, attempts=1, strategy="none", confidence=0.9, data=None):
    step = SimpleNamespace(success=success, status="completed", attempts=attempts,
                           recovery_strategy=strategy, tool_id="system.info", executed_tool_id=None)
    tool = SimpleNamespace(success=success, data=data or {}, tool_id="system.info")
    plan = SimpleNamespace(intent=SimpleNamespace(confidence=confidence, raw_input="revisar el sistema"))
    return SimpleNamespace(step_results=[step], tool_result=tool, plan=plan, error=error)


def test_successful_verified_result_does_not_interrupt():
    report = AdvisoryService(AdvisoryConfig()).analyze(_result())
    assert report is not None
    assert report.confidence_score >= 0.75
    assert report.should_notify is False


def test_failure_warns_but_never_blocks_or_executes():
    service = AdvisoryService(AdvisoryConfig())
    report = service.analyze(_result(error="timeout", success=False, attempts=3, strategy="fallback"))
    assert report is not None
    assert report.intervention_level == 2
    assert report.should_notify is True
    assert all(not callable(action.delegated_intent) for action in report.actions)


def test_layer_can_be_disabled():
    assert AdvisoryService(AdvisoryConfig(enabled=False)).analyze(_result()) is None


def test_advisory_exception_is_fail_open():
    class BrokenAdvisory:
        def analyze(self, result):
            raise RuntimeError("advisory unavailable")

    original = SimpleNamespace(advisory=None)
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator._advisory = BrokenAdvisory()
    assert orchestrator._attach_advisory(original) is original
    assert original.advisory is None


def test_stale_sources_are_explained():
    report = AdvisoryService(AdvisoryConfig(stale_after_hours=1)).analyze(
        _result(data={"sources": [{"id": "old", "updated_at": "2000-01-01T00:00:00Z"}]})
    )
    assert report is not None
    assert report.should_notify is True
    assert any("desactualizada" in insight.title.lower() for insight in report.insights)
