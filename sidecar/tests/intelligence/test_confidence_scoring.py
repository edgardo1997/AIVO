import pytest
from sentinel.intelligence.confidence_scorer import ConfidenceScorer


class TestConfidenceScorer:
    def test_basic_scoring(self):
        scorer = ConfidenceScorer()
        score = scorer.score("The answer is 42. This is because the calculation yields this result. Therefore, we can conclude that the system works correctly.")
        assert 0.0 <= score.overall <= 1.0
        assert score.model_id == ""
        assert score.provider == ""

    def test_scoring_with_model_info(self):
        scorer = ConfidenceScorer()
        score = scorer.score("Test response", model_id="gpt-4", provider="openai")
        assert score.model_id == "gpt-4"
        assert score.provider == "openai"

    def test_short_response_low_confidence(self):
        scorer = ConfidenceScorer()
        score = scorer.score("Yes")
        assert score.overall < 0.5

    def test_detailed_response_higher_confidence(self):
        scorer = ConfidenceScorer()
        detailed = (
            "The architecture has three main components. First, the frontend handles user interactions "
            "through a React-based interface. Second, the API gateway routes requests to microservices. "
            "Third, the database layer persists data using PostgreSQL. "
            "For example, when a user submits a form, the data flows through all three layers. "
            "According to the documentation, this pattern ensures scalability. "
            "The system uses caching to reduce latency by 40%."
        )
        score = scorer.score(detailed)
        assert score.overall >= 0.3

    def test_instruction_adherence(self):
        scorer = ConfidenceScorer()
        response = "The API uses RESTful principles with JSON responses."
        score = scorer.score(response, instruction="Describe the API architecture")
        assert score.instruction_adherence > 0.0

    def test_confidence_scoring_components(self):
        scorer = ConfidenceScorer()
        score = scorer.score("First, we analyze the requirements. Therefore, the design must consider scalability. For example, using microservices allows independent deployment.", instruction="Design a scalable system")
        assert score.reasoning_quality >= 0.0
        assert score.coherence >= 0.0
        assert score.instruction_adherence >= 0.0
        assert score.evidence_use >= 0.0
        assert score.detail_level >= 0.0

    def test_error_penalty(self):
        scorer = ConfidenceScorer()
        score = scorer.score("I cannot answer this. Sorry, I don't know. The answer might be incorrect.")
        assert score.error_count > 0
        assert score.overall < 0.5

    def test_model_history_boost(self):
        scorer = ConfidenceScorer(historical_data={"gpt-4": 0.8})
        scorer.update_model_history("gpt-4", 0.9)
        assert "gpt-4" in scorer._model_history
        assert scorer._model_history["gpt-4"] > 0.8

    def test_historical_data_updates_smoothly(self):
        scorer = ConfidenceScorer()
        scorer.update_model_history("qwen", 0.5)
        assert scorer._model_history["qwen"] == 0.5 * 0.3  # old=0, new=0.5 → 0*0.7 + 0.5*0.3
        scorer.update_model_history("qwen", 1.0)
        expected = 0.15 * 0.7 + 1.0 * 0.3  # old=0.15, new=1.0
        assert abs(scorer._model_history["qwen"] - expected) < 0.001

    def test_scores_are_bounded(self):
        scorer = ConfidenceScorer()
        score = scorer.score("A" * 1000)  # very long but low quality
        assert 0.0 <= score.overall <= 1.0
        assert 0.0 <= score.reasoning_quality <= 1.0
        assert 0.0 <= score.coherence <= 1.0
