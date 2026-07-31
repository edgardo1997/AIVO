import pytest
from sentinel.core.performance_intelligence import (
    PerformanceIntelligence,
    ExecutionMetrics,
    ModelPerformanceSummary,
)
from sentinel.core.feedback_engine import (
    FeedbackEngine,
    UserFeedback,
    FeedbackScore,
    FeedbackSummary,
)
from sentinel.core.model_ranking import (
    ModelRanking,
    ModelScore,
    ObservedCapabilities,
)
from sentinel.core.time_predictor import (
    TimePredictor,
    TimePrediction,
)
from sentinel.core import event_types


class TestPerformanceIntelligence:
    def test_record_metric(self):
        pi = PerformanceIntelligence()
        pi.record_metric(
            ExecutionMetrics(
                model_id="qwen-coder",
                task_type="coding",
                intent="write function",
                latency=2.5,
                tokens_used=500,
                cost=0.0,
                success=True,
            )
        )
        assert pi.total_records == 1

    def test_get_summary(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "task1", 1.0, 100, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "coding", "task2", 2.0, 200, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "coding", "task3", 3.0, 300, 0, False, error="timeout"))
        summaries = pi.get_summary("m1")
        assert len(summaries) == 1
        s = summaries[0]
        assert s.model_id == "m1"
        assert s.total_executions == 3
        assert s.successful_executions == 2
        assert s.failed_executions == 1
        assert s.success_rate == pytest.approx(2 / 3)
        assert s.avg_latency == pytest.approx(2.0)
        assert s.min_latency == 1.0
        assert s.max_latency == 3.0
        assert s.reliability_score == pytest.approx(66.7, rel=0.1)

    def test_get_summary_all_models(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 0.5, 50, 0, True))
        pi.record_metric(ExecutionMetrics("m2", "coding", "fix", 3.0, 300, 0, True))
        summaries = pi.get_summary()
        assert len(summaries) == 2

    def test_get_success_rate_no_data(self):
        pi = PerformanceIntelligence()
        assert pi.get_success_rate("unknown") == 0.0

    def test_get_avg_latency(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.5, 50, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi2", 2.5, 60, 0, True))
        assert pi.get_avg_latency("m1") == pytest.approx(2.0)

    def test_get_avg_latency_no_data(self):
        pi = PerformanceIntelligence()
        assert pi.get_avg_latency("unknown") == 0.0

    def test_get_metrics_by_model(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.0, 10, 0, True))
        pi.record_metric(ExecutionMetrics("m2", "coding", "fix", 2.0, 20, 0, True))
        assert len(pi.get_metrics(model_id="m1")) == 1
        assert len(pi.get_metrics(model_id="m2")) == 1
        assert len(pi.get_metrics()) == 2

    def test_get_metrics_by_task(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "fix", 2.0, 100, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 0.5, 20, 0, True))
        coding = pi.get_metrics_by_task("coding")
        assert len(coding) == 1
        assert coding[0].task_type == "coding"

    def test_clear(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.0, 10, 0, True))
        pi.clear()
        assert pi.total_records == 0

    def test_reliability_score_property(self):
        summary = ModelPerformanceSummary(
            model_id="m1", total_executions=10, successful_executions=9,
            failed_executions=1, success_rate=0.9, avg_latency=1.0,
            max_latency=2.0, min_latency=0.5, avg_tokens_used=100,
            avg_cost=0.0, total_cost=0.0,
        )
        assert summary.reliability_score == 90.0

    def test_reliability_score_no_data(self):
        summary = ModelPerformanceSummary(
            model_id="m1", total_executions=0, successful_executions=0,
            failed_executions=0, success_rate=0.0, avg_latency=0.0,
            max_latency=0.0, min_latency=0.0, avg_tokens_used=0,
            avg_cost=0.0, total_cost=0.0,
        )
        assert summary.reliability_score == 0.0

    def test_metrics_to_dict(self):
        m = ExecutionMetrics("m1", "coding", "fix", 1.5, 200, 0.002, True)
        d = m.to_dict()
        assert d["model_id"] == "m1"
        assert d["latency"] == 1.5
        assert d["success"] is True
        assert "timestamp" in d


class TestPerformanceIntelligenceTest1:
    """Test 1: Register successful execution — metric stored."""

    def test_successful_execution_stored(self):
        pi = PerformanceIntelligence()
        pi.record_metric(
            ExecutionMetrics("qwen-coder", "coding", "write function", 3.2, 500, 0, True)
        )
        assert pi.total_records == 1
        metrics = pi.get_metrics(model_id="qwen-coder")
        assert len(metrics) == 1
        m = metrics[0]
        assert m.model_id == "qwen-coder"
        assert m.success is True


class TestPerformanceIntelligenceTest2:
    """Test 2: Register failure — model loses ranking."""

    def test_failure_recorded(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("unstable-model", "coding", "fix bug", 8.0, 1000, 0, False, error="timeout"))
        pi.record_metric(ExecutionMetrics("unstable-model", "coding", "fix bug", 1.0, 100, 0, True))
        pi.record_metric(ExecutionMetrics("unstable-model", "coding", "fix bug", 9.0, 1000, 0, False, error="crash"))
        summary = pi.get_model_summary("unstable-model")
        assert summary is not None
        assert summary.failed_executions == 2
        assert summary.success_rate == pytest.approx(1 / 3)
        assert summary.reliability_score == pytest.approx(33.3, rel=0.1)
        assert len(summary.recent_errors) == 2


class TestFeedbackEngine:
    def test_record_positive_feedback(self):
        fe = FeedbackEngine()
        fe.record_feedback(
            UserFeedback(model_id="qwen", task_type="coding", score=FeedbackScore.POSITIVE)
        )
        assert fe.total_feedback == 1

    def test_record_negative_feedback(self):
        fe = FeedbackEngine()
        fe.record_feedback(
            UserFeedback(model_id="qwen", task_type="coding", score=FeedbackScore.NEGATIVE)
        )
        assert fe.total_feedback == 1

    def test_get_summary_positive_ratio(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.POSITIVE))
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.POSITIVE))
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.NEGATIVE))
        summaries = fe.get_summary(model_id="m1")
        assert len(summaries) == 1
        s = summaries[0]
        assert s.positive == 2
        assert s.negative == 1
        assert s.positive_ratio == pytest.approx(2 / 3)
        assert s.net_score == 1
        assert s.score_delta == pytest.approx(33.3, rel=0.1)

    def test_get_summary_filter_by_task(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.POSITIVE))
        fe.record_feedback(UserFeedback("m1", "chat", FeedbackScore.NEGATIVE))
        summaries = fe.get_summary(model_id="m1", task_type="coding")
        assert len(summaries) == 1
        assert summaries[0].task_type == "coding"

    def test_get_model_feedback(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.POSITIVE, user_id="u1"))
        fe.record_feedback(UserFeedback("m2", "chat", FeedbackScore.NEGATIVE, user_id="u2"))
        m1_feedback = fe.get_model_feedback("m1")
        assert len(m1_feedback) == 1
        assert m1_feedback[0].model_id == "m1"

    def test_get_positive_ratio_default(self):
        fe = FeedbackEngine()
        assert fe.get_positive_ratio("unknown") == 0.5

    def test_get_positive_ratio_computed(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.POSITIVE))
        assert fe.get_positive_ratio("m1") == 1.0

    def test_clear(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.POSITIVE))
        fe.clear()
        assert fe.total_feedback == 0

    def test_neutral_feedback(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("m1", "coding", FeedbackScore.NEUTRAL))
        summaries = fe.get_summary(model_id="m1")
        assert summaries[0].neutral == 1

    def test_feedback_summary_empty(self):
        fe = FeedbackEngine()
        assert fe.get_summary() == []

    def test_feedback_to_dict(self):
        fb = UserFeedback("m1", "coding", FeedbackScore.POSITIVE, comment="great", user_id="u1", conversation_id="c1")
        d = fb.to_dict()
        assert d["model_id"] == "m1"
        assert d["score"] == "positive"
        assert d["comment"] == "great"

    def test_score_delta_property(self):
        s = FeedbackSummary(model_id="m1", task_type="coding", total=5, positive=4, negative=1, neutral=0, positive_ratio=0.8, net_score=3)
        assert s.score_delta == pytest.approx(60.0)

    def test_feedback_engine_summary_sort(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("slow-model", "coding", FeedbackScore.NEGATIVE))
        fe.record_feedback(UserFeedback("fast-model", "coding", FeedbackScore.POSITIVE))
        fe.record_feedback(UserFeedback("fast-model", "coding", FeedbackScore.POSITIVE))
        summaries = fe.get_summary()
        assert summaries[0].model_id == "fast-model"
        assert summaries[1].model_id == "slow-model"


class TestFeedbackEngineTest3:
    """Test 3: Positive feedback — score increases."""

    def test_positive_feedback_increases_score(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("model-a", "coding", FeedbackScore.POSITIVE))
        fe.record_feedback(UserFeedback("model-a", "coding", FeedbackScore.POSITIVE))
        fe.record_feedback(UserFeedback("model-a", "coding", FeedbackScore.POSITIVE))
        summaries = fe.get_summary(model_id="model-a")
        assert summaries[0].positive_ratio == 1.0
        assert summaries[0].net_score == 3


class TestFeedbackEngineTest4:
    """Test 4: Negative feedback — score decreases."""

    def test_negative_feedback_decreases_score(self):
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("model-b", "automation", FeedbackScore.POSITIVE))
        fe.record_feedback(UserFeedback("model-b", "automation", FeedbackScore.NEGATIVE))
        fe.record_feedback(UserFeedback("model-b", "automation", FeedbackScore.NEGATIVE))
        summaries = fe.get_summary(model_id="model-b")
        assert summaries[0].positive_ratio == pytest.approx(1 / 3)
        assert summaries[0].net_score == -1


class TestModelRanking:
    def test_compute_scores_without_perf(self):
        ranking = ModelRanking()
        scores = ranking.compute_scores()
        assert scores == []

    def test_compute_scores_with_perf(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("model-a", "coding", "task", 1.0, 100, 0, True))
        pi.record_metric(ExecutionMetrics("model-a", "coding", "task", 2.0, 200, 0, True))
        pi.record_metric(ExecutionMetrics("model-a", "coding", "task", 1.5, 150, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        scores = ranking.compute_scores()
        assert len(scores) == 1
        s = scores[0]
        assert s.model_id == "model-a"
        assert s.performance_score > 0
        assert s.total_executions == 3
        assert s.rank == 1

    def test_ranking_order(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("slow-model", "coding", "task", 10.0, 1000, 0.002, True))
        pi.record_metric(ExecutionMetrics("slow-model", "coding", "task", 12.0, 1200, 0.002, False, error="err"))
        pi.record_metric(ExecutionMetrics("fast-model", "coding", "task", 0.5, 50, 0, True))
        pi.record_metric(ExecutionMetrics("fast-model", "coding", "task", 0.8, 80, 0, True))
        pi.record_metric(ExecutionMetrics("fast-model", "coding", "task", 0.6, 60, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        scores = ranking.compute_scores()
        scores.sort(key=lambda s: s.performance_score, reverse=True)
        assert scores[0].model_id == "fast-model"
        assert scores[0].performance_score > scores[1].performance_score

    def test_get_top_k(self):
        pi = PerformanceIntelligence()
        for i in range(5):
            pi.record_metric(ExecutionMetrics(f"model-{i}", "chat", "hi", 1.0, 10, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        ranking.compute_scores()
        top3 = ranking.get_top_k(3)
        assert len(top3) == 3

    def test_get_model_score(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.0, 10, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        ranking.compute_scores()
        score = ranking.get_model_score("m1")
        assert score is not None
        assert score.model_id == "m1"

    def test_get_model_score_unknown(self):
        ranking = ModelRanking()
        assert ranking.get_model_score("unknown") is None

    def test_scores_property(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.0, 10, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        ranking.compute_scores()
        assert "m1" in ranking.scores

    def test_declared_vs_observed(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 1.0, 100, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 2.0, 200, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        ranking.compute_scores()
        result = ranking.get_declared_vs_observed("m1", {"coding": True, "reasoning": False})
        assert result["model_id"] == "m1"
        assert "observed" in result

    def test_declared_vs_observed_no_score(self):
        ranking = ModelRanking()
        result = ranking.get_declared_vs_observed("unknown", {"coding": True})
        assert result["model_id"] == "unknown"

    def test_get_audit_log(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.0, 10, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        assert ranking.get_audit_log() == []
        ranking.compute_scores()
        assert len(ranking.get_audit_log()) == 1
        assert ranking.get_audit_log()[0]["action"] == "rank_update"

    def test_observed_capabilities_coding(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 1.0, 100, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 2.0, 200, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 3.0, 300, 0, False, error="err"))
        ranking = ModelRanking(performance_intelligence=pi)
        ranking.compute_scores()
        score = ranking.get_model_score("m1")
        assert score.observed_capabilities.supports_coding_score == pytest.approx(66.7, rel=0.1)

    def test_feedback_integrates_into_scores(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.0, 10, 0, True))
        fe = FeedbackEngine()
        fe.record_feedback(UserFeedback("m1", "chat", FeedbackScore.POSITIVE))
        ranking = ModelRanking(performance_intelligence=pi, feedback_engine=fe)
        scores = ranking.compute_scores()
        assert len(scores) == 1
        assert scores[0].feedback_count > 0
        assert scores[0].feedback_positive_ratio == 1.0


class TestModelRankingTest5:
    """Test 5: Dynamic ranking — faster model ranks above slower model."""

    def test_faster_model_outranks_slower(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("Model-A", "coding", "task", 8.0, 1000, 0.002, True))
        pi.record_metric(ExecutionMetrics("Model-A", "coding", "task", 7.0, 900, 0.002, True))
        pi.record_metric(ExecutionMetrics("Model-B", "coding", "task", 2.0, 300, 0, True))
        pi.record_metric(ExecutionMetrics("Model-B", "coding", "task", 3.0, 400, 0, True))
        ranking = ModelRanking(performance_intelligence=pi)
        scores = ranking.compute_scores()
        scores.sort(key=lambda s: s.rank)
        assert scores[0].model_id == "Model-B"
        assert scores[1].model_id == "Model-A"


class TestTimePredictor:
    def test_predict_without_data(self):
        tp = TimePredictor()
        pred = tp.predict("unknown-model", "coding")
        assert pred.estimated_seconds == 10.0
        assert pred.confidence == 0.1
        assert pred.sample_count == 0

    def test_predict_with_data(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 2.0, 200, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 3.0, 300, 0, True))
        pi.record_metric(ExecutionMetrics("m1", "coding", "task", 2.5, 250, 0, True))
        tp = TimePredictor(performance_intelligence=pi)
        pred = tp.predict("m1", "coding")
        assert pred.model_id == "m1"
        assert pred.task_type == "coding"
        assert pred.estimated_seconds == pytest.approx(2.5, rel=0.1)
        assert pred.confidence > 0.1
        assert pred.sample_count == 3

    def test_predict_falls_back_to_all_model(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "chat", "hi", 1.0, 50, 0, True))
        tp = TimePredictor(performance_intelligence=pi)
        pred = tp.predict("m1", "coding")
        assert pred.sample_count == 1

    def test_predict_with_complexity_hint(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "fix", 5.0, 500, 0, True))
        tp = TimePredictor(performance_intelligence=pi)
        pred = tp.predict("m1", "coding", complexity_hint="complex")
        assert pred.complexity_factor == 2.0
        assert pred.estimated_seconds == pytest.approx(10.0, rel=0.1)

    def test_predict_with_simple_complexity(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "fix", 5.0, 500, 0, True))
        tp = TimePredictor(performance_intelligence=pi)
        pred = tp.predict("m1", "coding", complexity_hint="simple")
        assert pred.complexity_factor == 0.5
        assert pred.estimated_seconds == pytest.approx(2.5, rel=0.1)

    def test_predict_by_complexity_line_count(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("m1", "coding", "fix", 5.0, 500, 0, True))
        tp = TimePredictor(performance_intelligence=pi)
        pred = tp.predict_by_complexity("m1", "coding", line_count=50000)
        assert pred.complexity_factor == 4.0

    def test_estimated_display_seconds(self):
        pred = TimePrediction(estimated_seconds=30, confidence=0.5, min_estimate=10, max_estimate=50, sample_count=5, model_id="m1", task_type="chat")
        assert "seconds" in pred.estimated_display

    def test_estimated_display_minutes(self):
        pred = TimePrediction(estimated_seconds=120, confidence=0.5, min_estimate=60, max_estimate=180, sample_count=5, model_id="m1", task_type="chat")
        assert "minutes" in pred.estimated_display

    def test_estimated_display_hours(self):
        pred = TimePrediction(estimated_seconds=7200, confidence=0.5, min_estimate=3600, max_estimate=10800, sample_count=5, model_id="m1", task_type="chat")
        assert "hours" in pred.estimated_display

    def test_to_dict(self):
        pred = TimePrediction(estimated_seconds=30, confidence=0.8, min_estimate=20, max_estimate=40, sample_count=10, model_id="m1", task_type="chat")
        d = pred.to_dict()
        assert d["estimated_seconds"] == 30
        assert d["confidence"] == 0.8
        assert d["sample_count"] == 10

    def test_resolve_complexity_unknown(self):
        assert TimePredictor._resolve_complexity("unknown_hint") == 1.0

    def test_resolve_complexity_none(self):
        assert TimePredictor._resolve_complexity(None) == 1.0

    def test_no_perf_provided(self):
        tp = TimePredictor()
        pred = tp.predict("m1", "coding")
        assert pred.estimated_seconds == 10.0


class TestTimePredictorTest6:
    """Test 6: Time prediction — estimate generated."""

    def test_time_prediction_generated(self):
        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("qwen-coder", "analysis", "analyze project", 30.0, 5000, 0, True))
        pi.record_metric(ExecutionMetrics("qwen-coder", "analysis", "analyze project", 45.0, 6000, 0, True))
        tp = TimePredictor(performance_intelligence=pi)
        pred = tp.predict_by_complexity("qwen-coder", "analysis", line_count=50000)
        assert pred.estimated_seconds > 0
        assert pred.sample_count == 2
        assert 0 < pred.confidence <= 1.0
        assert pred.estimated_display is not None


class TestIntelligenceOrchestratorIntegration:
    def test_set_performance_intelligence(self):
        from sentinel.core.intelligence_orchestrator import IntelligenceOrchestrator
        io = IntelligenceOrchestrator()
        pi = PerformanceIntelligence()
        io.set_performance_intelligence(pi)
        assert io._performance_intelligence is pi

    def test_set_model_ranking(self):
        from sentinel.core.intelligence_orchestrator import IntelligenceOrchestrator
        io = IntelligenceOrchestrator()
        pi = PerformanceIntelligence()
        ranking = ModelRanking(performance_intelligence=pi)
        io.set_model_ranking(ranking)
        assert io._model_ranking is ranking

    def test_set_time_predictor(self):
        from sentinel.core.intelligence_orchestrator import IntelligenceOrchestrator
        io = IntelligenceOrchestrator()
        tp = TimePredictor()
        io.set_time_predictor(tp)
        assert io._time_predictor is tp

    def test_audit_log(self):
        from sentinel.core.intelligence_orchestrator import IntelligenceOrchestrator
        io = IntelligenceOrchestrator()
        assert io.audit_log == []

    def test_orchestrate_records_audit(self):
        from sentinel.core.intelligence_orchestrator import (
            IntelligenceOrchestrator, IntelligenceDecision, ExecutionStrategy,
        )
        from sentinel.core.model_registry import ModelRegistry
        from sentinel.core.capability_engine import CapabilityEngine, IntentType
        from sentinel.core.intent_engine_v2 import ClassifiedIntent, IntentCategory
        from sentinel.models import ModelMetadata, ModelStatus

        registry = ModelRegistry()
        registry.register(ModelMetadata(id="test-model", provider="test", supports_coding=True, supports_reasoning=True, status=ModelStatus.AVAILABLE))
        io = IntelligenceOrchestrator(model_registry=registry)
        intent = ClassifiedIntent(category=IntentCategory.CODING, raw_input="write code", confidence=0.9)
        decision = io.orchestrate(intent)
        assert decision.status == "success"
        assert decision.model_id == "test-model"
        assert len(io.audit_log) == 1
        assert io.audit_log[0]["action"] == "model_selected"


class TestIntelligenceOrchestratorTest7:
    """Test 7: Explainable decision — includes model, reasons, metrics used."""

    def test_decision_includes_reasoning(self):
        from sentinel.core.intelligence_orchestrator import (
            IntelligenceOrchestrator, IntelligenceDecision, ExecutionStrategy,
        )
        from sentinel.core.model_registry import ModelRegistry
        from sentinel.core.capability_engine import CapabilityEngine, IntentType
        from sentinel.core.intent_engine_v2 import ClassifiedIntent, IntentCategory
        from sentinel.models import ModelMetadata, ModelStatus

        registry = ModelRegistry()
        registry.register(ModelMetadata(id="qwen-coder", provider="ollama", supports_coding=True, supports_reasoning=True, speed="fast", cost=0.0, local=True, status=ModelStatus.AVAILABLE))

        pi = PerformanceIntelligence()
        pi.record_metric(ExecutionMetrics("qwen-coder", "coding", "write code", 2.5, 500, 0, True))
        pi.record_metric(ExecutionMetrics("qwen-coder", "coding", "fix bug", 3.0, 600, 0, True))
        pi.record_metric(ExecutionMetrics("qwen-coder", "coding", "refactor", 1.5, 300, 0, True))

        ranking = ModelRanking(performance_intelligence=pi)
        ranking.compute_scores()

        tp = TimePredictor(performance_intelligence=pi)

        io = IntelligenceOrchestrator(model_registry=registry)
        io.set_performance_intelligence(pi)
        io.set_model_ranking(ranking)
        io.set_time_predictor(tp)

        intent = ClassifiedIntent(category=IntentCategory.CODING, raw_input="write function", confidence=0.95)
        decision = io.orchestrate(intent, context={"complexity": "moderate"})

        assert decision.model_id == "qwen-coder"
        assert decision.reasoning is not None and len(decision.reasoning) > 0
        assert "qwen-coder" in decision.reasoning
        assert decision.status == "success"
        assert decision.confidence > 0

        # Verify reasoning includes performance data
        reasoning = decision.reasoning
        assert "Performance" in reasoning or "Reliability" in reasoning or "Success rate" in reasoning or "Estimated time" in reasoning

        decision_dict = decision.to_dict()
        assert "model_id" in decision_dict
        assert "reasoning" in decision_dict
        assert "execution_strategy" in decision_dict
        assert "confidence" in decision_dict


class TestEventTypes:
    def test_new_event_types_exist(self):
        assert hasattr(event_types, "MODEL_EXECUTION_STARTED")
        assert hasattr(event_types, "MODEL_EXECUTION_COMPLETED")
        assert hasattr(event_types, "MODEL_EXECUTION_FAILED")
        assert hasattr(event_types, "USER_FEEDBACK_RECEIVED")
        assert hasattr(event_types, "MODEL_RANKING_UPDATED")

    def test_new_event_types_in_all_events(self):
        from sentinel.core.event_registry import EventRegistry
        registry = EventRegistry()
        assert registry.is_valid(event_types.MODEL_EXECUTION_STARTED)
        assert registry.is_valid(event_types.MODEL_EXECUTION_COMPLETED)
        assert registry.is_valid(event_types.MODEL_EXECUTION_FAILED)
        assert registry.is_valid(event_types.USER_FEEDBACK_RECEIVED)
        assert registry.is_valid(event_types.MODEL_RANKING_UPDATED)


class TestObservedCapabilities:
    def test_defaults(self):
        oc = ObservedCapabilities()
        assert oc.supports_coding_score == 0.0
        assert oc.supports_reasoning_score == 0.0
        assert oc.sample_count == 0


class TestExecutionMetrics:
    def test_default_timestamp(self):
        m = ExecutionMetrics("m1", "chat", "hi", 1.0, 10, 0, True)
        assert m.timestamp == ""
        d = m.to_dict()
        assert d["timestamp"] != ""


class TestPerformanceIntelligenceEventSubscription:
    def test_subscribe_to_events_no_bus(self):
        pi = PerformanceIntelligence()
        pi.subscribe_to_events()
        assert pi._subscribed is False

    def test_event_names(self):
        assert event_types.MODEL_EXECUTION_STARTED == "model.execution.started"
        assert event_types.MODEL_EXECUTION_COMPLETED == "model.execution.completed"
        assert event_types.MODEL_EXECUTION_FAILED == "model.execution.failed"
        assert event_types.USER_FEEDBACK_RECEIVED == "user.feedback.received"
        assert event_types.MODEL_RANKING_UPDATED == "model.ranking.updated"
