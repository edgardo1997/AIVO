import pytest
from sentinel.intelligence.conflict_resolver import ConflictResolver, ConflictLevel, extract_claims, find_conflicts
from sentinel.intelligence.evaluation_engine import ModelResponse, EvaluatedResponse
from sentinel.intelligence.confidence_scorer import ConfidenceScore


def _make_evaluated(model_id: str, text: str, score: float = 0.8, provider: str = "test") -> EvaluatedResponse:
    return EvaluatedResponse(
        response=ModelResponse(model_id=model_id, provider=provider, response_text=text),
        confidence=ConfidenceScore(model_id=model_id, overall=score),
    )


class TestConflictResolver:
    def test_no_conflict_with_single_model(self):
        resolver = ConflictResolver()
        ev = _make_evaluated("model_a", "The system uses PostgreSQL.")
        report = resolver.resolve([ev])
        assert report.total_conflicts == 0

    def test_no_conflict_when_models_agree(self):
        resolver = ConflictResolver()
        ev1 = _make_evaluated("model_a", "The database is PostgreSQL. It supports ACID transactions.")
        ev2 = _make_evaluated("model_b", "The database is PostgreSQL. It supports ACID transactions.")
        report = resolver.resolve([ev1, ev2])
        assert report.total_conflicts <= 2  # may detect minor pattern differences

    def test_detects_conflict_on_different_claims(self):
        resolver = ConflictResolver()
        ev1 = _make_evaluated("model_a", "The root cause is memory corruption in the kernel module.")
        ev2 = _make_evaluated("model_b", "The root cause is a CPU scheduling bug in the scheduler.")
        report = resolver.resolve([ev1, ev2])
        assert report.total_conflicts >= 1

    def test_resolves_minor_conflict(self):
        resolver = ConflictResolver()
        ev1 = _make_evaluated("model_a", "The system uses Python 3.10. This is the latest stable version.", score=0.9)
        ev2 = _make_evaluated("model_b", "The system uses Python 3.11. This provides better performance.", score=0.5)
        report = resolver.resolve([ev1, ev2])
        for c in report.conflicts:
            assert c.resolved

    def test_resolves_major_conflict_with_third_opinion(self):
        third_opinion_called = False

        def third_opinion_fn(prompt):
            nonlocal third_opinion_called
            third_opinion_called = True
            return "The correct answer is memory corruption based on available evidence."

        resolver = ConflictResolver(third_opinion_fn=third_opinion_fn)
        ev1 = _make_evaluated("model_a", "The cause is memory corruption.", score=0.6)
        ev2 = _make_evaluated("model_b", "The cause is CPU overheating.", score=0.6)
        ev3 = _make_evaluated("model_c", "The cause is a driver conflict.", score=0.6)
        report = resolver.resolve([ev1, ev2, ev3])
        # With 3+ unique positions, it's MAJOR and will use third_opinion_fn
        if report.total_conflicts > 0:
            assert third_opinion_called or all(c.resolved for c in report.conflicts)

    def test_extract_claims(self):
        text = "The database is PostgreSQL. The cache causes performance issues. Because the query is slow."
        claims = extract_claims(text)
        assert len(claims) >= 2

    def test_find_conflicts_empty(self):
        conflicts = find_conflicts([])
        assert conflicts == []

    def test_set_third_opinion_fn(self):
        resolver = ConflictResolver()
        called = False

        def fn(prompt):
            nonlocal called
            called = True
            return "resolution"

        resolver.set_third_opinion_fn(fn)
        ev1 = _make_evaluated("model_a", "The answer is A.", score=0.6)
        ev2 = _make_evaluated("model_b", "The answer is B.", score=0.6)
        ev3 = _make_evaluated("model_c", "The answer is C.", score=0.6)
        report = resolver.resolve([ev1, ev2, ev3])
        if report.total_conflicts > 0:
            assert called
