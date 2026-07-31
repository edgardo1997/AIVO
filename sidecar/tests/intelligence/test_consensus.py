import pytest
from sentinel.intelligence.consensus_engine import ConsensusEngine, extract_conclusion, extract_key_sentences
from sentinel.intelligence.evaluation_engine import EvaluationEngine, ModelResponse, EvaluatedResponse
from sentinel.intelligence.confidence_scorer import ConfidenceScorer


def _make_evaluated(model_id: str, text: str, provider: str = "test", duration_ms: float = 1000.0, cost: float = 0.0) -> EvaluatedResponse:
    scorer = ConfidenceScorer()
    score = scorer.score(text, model_id=model_id, provider=provider)
    return EvaluatedResponse(
        response=ModelResponse(model_id=model_id, provider=provider, response_text=text, duration_ms=duration_ms, cost=cost, success=True),
        confidence=score,
    )


class TestConsensusEngine:
    def test_empty_list_returns_empty(self):
        engine = ConsensusEngine(EvaluationEngine())
        result = engine.build_consensus([])
        assert result.final_answer == ""
        assert result.confidence == 0.0

    def test_single_model_result(self):
        engine = ConsensusEngine(EvaluationEngine())
        ev = _make_evaluated("model_a", "The system architecture uses microservices with an API gateway for routing requests between services.")
        result = engine.build_consensus([ev])
        assert result.final_answer != ""
        assert result.confidence > 0.0
        assert result.primary_model == "model_a"
        assert result.total_evaluated == 1

    def test_multi_model_result(self):
        engine = ConsensusEngine(EvaluationEngine())
        evs = [
            _make_evaluated("model_a", "The database should be PostgreSQL for ACID compliance. This ensures data integrity.", duration_ms=2000, cost=0.01),
            _make_evaluated("model_b", "PostgreSQL is recommended for this use case due to its reliability and performance characteristics.", duration_ms=1000, cost=0.0),
        ]
        result = engine.build_consensus(evs)
        assert result.final_answer != ""
        assert result.confidence > 0.0
        assert result.primary_model in ("model_a", "model_b")
        assert len(result.contributing_models) >= 1

    def test_consensus_includes_score_breakdown(self):
        engine = ConsensusEngine(EvaluationEngine())
        evs = [
            _make_evaluated("model_a", "The best approach is to use a layered architecture with clear separation of concerns between each layer.", duration_ms=500, cost=0.0),
            _make_evaluated("model_b", "A layered architecture provides the best separation of concerns for this type of application.", duration_ms=1500, cost=0.005),
        ]
        result = engine.build_consensus(evs)
        assert len(result.score_breakdown) == 2
        for entry in result.score_breakdown:
            assert "model_id" in entry
            assert "adjusted_score" in entry
            assert "confidence" in entry

    def test_extract_conclusion_from_text(self):
        text = "The system uses microservices. This provides scalability. In conclusion, the architecture is well-designed."
        conclusion = extract_conclusion(text)
        assert "well-designed" in conclusion or "microservices" in conclusion

    def test_extract_key_sentences(self):
        text = "The system uses a microservices architecture for scalability. This approach enables independent deployment of each service. Load balancing ensures optimal resource utilization across the cluster."
        sentences = extract_key_sentences(text)
        assert len(sentences) == 3

    def test_consensus_result_serialization(self):
        engine = ConsensusEngine(EvaluationEngine())
        ev = _make_evaluated("model_a", "Test response for serialization testing purposes.")
        result = engine.build_consensus([ev])
        d = result.to_dict()
        assert "final_answer" in d
        assert "confidence" in d
        assert "primary_model" in d
        assert "score_breakdown" in d
