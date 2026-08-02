import pytest
from sentinel.core.model_coordinator import (
    ModelCoordinator,
    ModelTask,
    MultiModelPlan,
    ModelTaskResult,
    MultiModelResult,
    ExecutionStrategy,
    TASK_DECOMPOSITION_RULES,
)
from sentinel.core.fusion_engine import FusionEngine, FusionResult, FusionFinding, FusionConflict


# ─────────────────────────────────────────────
# ModelTask
# ─────────────────────────────────────────────
class TestModelTask:
    def test_defaults(self):
        t = ModelTask()
        assert t.task_id == ""
        assert t.objective == ""
        assert t.required_capabilities == []

    def test_to_dict(self):
        t = ModelTask(
            task_id="sec1",
            name="security_review",
            objective="analyze risks",
            required_capabilities=["reasoning"],
            preferred_model="nemotron",
            dependencies=["arch1"],
        )
        d = t.to_dict()
        assert d["task_id"] == "sec1"
        assert d["name"] == "security_review"
        assert d["required_capabilities"] == ["reasoning"]
        assert d["dependencies"] == ["arch1"]


# ─────────────────────────────────────────────
# MultiModelPlan
# ─────────────────────────────────────────────
class TestMultiModelPlan:
    def test_empty(self):
        plan = MultiModelPlan()
        assert plan.tasks == []
        assert plan.execution_strategy == ExecutionStrategy.PARALLEL

    def test_add_task(self):
        plan = MultiModelPlan()
        plan.add_task(ModelTask(task_id="t1"))
        assert len(plan.tasks) == 1

    def test_has_dependencies(self):
        plan = MultiModelPlan()
        plan.add_task(ModelTask(task_id="t1"))
        assert plan.has_dependencies() is False
        plan.add_task(ModelTask(task_id="t2", dependencies=["t1"]))
        assert plan.has_dependencies() is True

    def test_independent_tasks(self):
        plan = MultiModelPlan()
        plan.add_task(ModelTask(task_id="t1"))
        plan.add_task(ModelTask(task_id="t2", dependencies=["t1"]))
        indep = plan.independent_tasks()
        assert len(indep) == 1
        assert indep[0].task_id == "t1"

    def test_to_dict(self):
        plan = MultiModelPlan(
            tasks=[ModelTask(task_id="t1")],
            execution_strategy=ExecutionStrategy.PARALLEL,
        )
        d = plan.to_dict()
        assert d["task_count"] == 1
        assert d["execution_strategy"] == "parallel"


# ─────────────────────────────────────────────
# ModelTaskResult / MultiModelResult
# ─────────────────────────────────────────────
class TestModelTaskResult:
    def test_defaults(self):
        r = ModelTaskResult()
        assert r.success is True
        assert r.error == ""

    def test_to_dict(self):
        r = ModelTaskResult(
            task_id="t1", task_name="code", model_id="qwen",
            provider="local", response="looks good", success=True,
        )
        d = r.to_dict()
        assert d["task_name"] == "code"
        assert d["success"] is True


class TestMultiModelResult:
    def test_all_successful(self):
        r = MultiModelResult(
            results=[ModelTaskResult(success=True), ModelTaskResult(success=True)],
            total_tasks=2, successful=2,
        )
        assert r.all_successful is True
        assert r.partial_completion is False

    def test_partial(self):
        r = MultiModelResult(
            results=[ModelTaskResult(success=True), ModelTaskResult(success=False)],
            total_tasks=2, successful=1, failed=1,
        )
        assert r.all_successful is False
        assert r.partial_completion is True

    def test_all_failed(self):
        r = MultiModelResult(
            results=[ModelTaskResult(success=False)],
            total_tasks=1, successful=0, failed=1,
        )
        assert r.all_failed is True


# ─────────────────────────────────────────────
# ModelCoordinator
# ─────────────────────────────────────────────
class FakeRegistry:
    def __init__(self, models):
        self._models = models

    def list_available(self):
        return self._models

    def find_candidates(self, caps):
        return [m for m in self._models if all(m.has_capability(c) for c in caps)]


class FakeModel:
    def __init__(self, id, provider="test", coding=False, reasoning=False, speed="fast", cost=0.0, local=False):
        self.id = id
        self.provider = provider
        self.supports_coding = coding
        self.supports_reasoning = reasoning
        self.supports_tool_calling = False
        self.supports_vision = False
        self.supports_embeddings = False
        self.speed = speed
        self.cost = cost
        self.local = local
        self.status = "available"

    def has_capability(self, cap):
        return getattr(self, f"supports_{cap}", False)


class TestModelCoordinator:
    def test_can_coordinate_reasoning(self):
        class FakeIntent:
            category = "REASONING"
        coord = ModelCoordinator()
        assert coord.can_coordinate(FakeIntent()) is True

    def test_can_coordinate_action_returns_false(self):
        class FakeIntent:
            category = "ACTION"
        coord = ModelCoordinator()
        assert coord.can_coordinate(FakeIntent()) is False

    def test_decompose_project_analysis(self):
        coord = ModelCoordinator()
        plan = coord.decompose("analyze my project", capabilities=["coding", "reasoning"])
        assert len(plan.tasks) >= 3
        names = [t.name for t in plan.tasks]
        assert "architecture_review" in names
        assert "security_review" in names
        assert "code_review" in names

    def test_decompose_security(self):
        coord = ModelCoordinator()
        plan = coord.decompose("check security vulnerabilities")
        assert len(plan.tasks) >= 3
        names = [t.name for t in plan.tasks]
        assert "dependency_check" in names
        assert "permission_audit" in names
        assert "data_safety" in names

    def test_decompose_empty_message(self):
        coord = ModelCoordinator()
        plan = coord.decompose("")
        assert len(plan.tasks) >= 1

    def test_decompose_without_capabilities(self):
        coord = ModelCoordinator()
        plan = coord.decompose("analyze my app")
        assert len(plan.tasks) >= 1

    def test_decompose_research(self):
        coord = ModelCoordinator()
        plan = coord.decompose("research this topic")
        names = [t.name for t in plan.tasks]
        assert "fact_checking" in names
        assert "deep_analysis" in names

    def test_select_specialist_no_registry(self):
        coord = ModelCoordinator()
        task = ModelTask(required_capabilities=["reasoning"])
        assert coord.select_specialist(task) is None

    def test_select_specialist_with_match(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("model-a", coding=True, reasoning=True),
            FakeModel("model-b", coding=False, reasoning=False),
        ]))
        task = ModelTask(required_capabilities=["reasoning"])
        model = coord.select_specialist(task)
        assert model is not None
        assert model.id == "model-a"

    def test_select_specialist_no_match(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("model-a", coding=False, reasoning=False),
        ]))
        task = ModelTask(required_capabilities=["reasoning"])
        model = coord.select_specialist(task)
        assert model is None

    def test_assign_models(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("specialist", coding=True, reasoning=True),
        ]))
        plan = MultiModelPlan(tasks=[
            ModelTask(task_id="t1", name="arch1", required_capabilities=["reasoning"]),
            ModelTask(task_id="t2", name="code1", required_capabilities=["coding"]),
        ])
        assignments = coord.assign_models(plan)
        assert "t1" in assignments
        assert "t2" in assignments
        assert plan.tasks[0].preferred_model == "specialist"

    def test_build_task_prompt(self):
        coord = ModelCoordinator()
        task = ModelTask(name="security", objective="find risks")
        prompt = coord.build_task_prompt(task, "check my app", {"extra": "info"})
        assert "Objective: find risks" in prompt
        assert "check my app" in prompt
        assert "extra: info" in prompt

    def test_execute_task_success(self):
        coord = ModelCoordinator()
        task = ModelTask(task_id="t1", name="test", objective="do thing")

        def fake_chat(messages, **kw):
            return {"response": "result OK", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        import asyncio
        result = asyncio.run(coord.execute_task(task, "hello", FakeModel("m1"), fake_chat))
        assert result.success is True
        assert result.response == "result OK"

    def test_execute_task_failure(self):
        coord = ModelCoordinator()
        task = ModelTask(task_id="t1", name="test")

        def failing_chat(messages, **kw):
            raise RuntimeError("API error")

        import asyncio
        result = asyncio.run(coord.execute_task(task, "hello", FakeModel("m1"), failing_chat))
        assert result.success is False
        assert "API error" in result.error

    def test_execute_plan_parallel(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("m1", coding=True, reasoning=True),
        ]))
        plan = MultiModelPlan(
            tasks=[
                ModelTask(task_id="t1", name="arch", required_capabilities=["reasoning"]),
                ModelTask(task_id="t2", name="code", required_capabilities=["coding"]),
            ],
            execution_strategy=ExecutionStrategy.PARALLEL,
        )

        def fake_chat(messages, **kw):
            return {"response": "ok", "usage": {"prompt_tokens": 5, "completion_tokens": 5}}

        import asyncio
        result = asyncio.run(coord.execute_plan(plan, "test", fake_chat))
        assert result.total_tasks == 2
        assert result.successful == 2

    def test_execute_plan_partial_failure(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("m1", coding=True, reasoning=True),
        ]))
        plan = MultiModelPlan(
            tasks=[
                ModelTask(task_id="t1", name="arch", required_capabilities=["reasoning"]),
                ModelTask(task_id="t2", name="code", required_capabilities=["coding"]),
            ],
        )

        call_count = [0]

        def fake_chat(messages, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"response": "ok", "usage": {}}
            raise RuntimeError("second failed")

        import asyncio
        result = asyncio.run(coord.execute_plan(plan, "test", fake_chat))
        assert result.total_tasks == 2
        assert result.successful == 1
        assert result.failed == 1
        assert result.partial_completion is True

    def test_execute_plan_all_fail(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("m1", coding=True),
        ]))
        plan = MultiModelPlan(tasks=[
            ModelTask(task_id="t1", name="arch", required_capabilities=["reasoning"]),
        ])
        # No model for this capability
        import asyncio
        result = asyncio.run(coord.execute_plan(plan, "test", lambda *a, **kw: {}))
        assert result.total_tasks == 1
        assert result.failed == 1

    def test_execute_plan_sequential_with_deps(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("m1", coding=True, reasoning=True),
        ]))
        plan = MultiModelPlan(
            tasks=[
                ModelTask(task_id="t1", name="first", required_capabilities=["reasoning"]),
                ModelTask(task_id="t2", name="second", required_capabilities=["coding"], dependencies=["t1"]),
            ],
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
        )
        call_order = []

        def fake_chat(messages, **kw):
            call_order.append(messages[0]["content"])
            return {"response": "ok", "usage": {}}

        import asyncio
        result = asyncio.run(coord.execute_plan(plan, "test", fake_chat))
        assert result.total_tasks == 2
        assert result.successful == 2

    def test_add_rule(self):
        coord = ModelCoordinator()
        coord.add_decomposition_rule("custom", [{"name": "custom_task", "capabilities": ["reasoning"]}])
        rules = coord.get_decomposition_rules()
        assert "custom" in rules

    def test_task_without_preferred_model_uses_assignment(self):
        coord = ModelCoordinator()
        coord.set_model_registry(FakeRegistry([
            FakeModel("specialist", reasoning=True),
        ]))
        task = ModelTask(task_id="t1", name="test", required_capabilities=["reasoning"])
        model = coord.select_specialist(task)
        assert model is not None
        assert task.preferred_model == "specialist"


# ─────────────────────────────────────────────
# FusionEngine
# ─────────────────────────────────────────────
class TestFusionEngine:
    def test_empty_results(self):
        engine = FusionEngine()
        result = engine.fuse([])
        assert result.finding_count == 0
        assert "No results" in result.summary

    def test_single_success(self):
        engine = FusionEngine()
        results = [ModelTaskResult(
            task_id="t1", task_name="arch", model_id="m1",
            response="The architecture follows MVC pattern with clear separation of concerns. "
                     "Models handle data, views handle presentation.",
            success=True,
        )]
        result = engine.fuse(results)
        assert result.finding_count >= 1
        assert "architecture" in result.categories

    def test_multiple_results(self):
        engine = FusionEngine()
        results = [
            ModelTaskResult(task_id="t1", task_name="arch", model_id="m1",
                            response="Clean architecture with modular design. Dependencies are well managed.",
                            success=True),
            ModelTaskResult(task_id="t2", task_name="security", model_id="m2",
                            response="Found potential XSS vulnerability in user input handling.",
                            success=True),
        ]
        result = engine.fuse(results)
        assert result.finding_count >= 2
        assert len(result.sources) == 2

    def test_failed_task_included(self):
        engine = FusionEngine()
        results = [
            ModelTaskResult(task_id="t1", task_name="arch", model_id="m1",
                            response="ok", success=True),
            ModelTaskResult(task_id="t2", task_name="security", model_id="m2",
                            response="", success=False, error="timeout"),
        ]
        result = engine.fuse(results)
        findings = engine.find_by_category(result, "error")
        assert len(findings) >= 1
        assert "timeout" in findings[0].detail

    def test_classification(self):
        engine = FusionEngine()
        assert engine._classify("the architecture uses modules") == "architecture"
        assert engine._classify("found a security vulnerability") == "security"
        assert engine._classify("code quality is acceptable") == "code_quality"
        assert engine._classify("some random text") == "general"

    def test_severity_assessment(self):
        engine = FusionEngine()
        assert engine._assess_severity("critical vulnerability found", "security") == "critical"
        assert engine._assess_severity("should consider refactoring", "code_quality") == "warning"
        assert engine._assess_severity("looks fine", "architecture") == "info"

    def test_conflict_detection(self):
        engine = FusionEngine()
        findings = [
            FusionFinding(source_task="security", category="security", detail="Found vulnerability in auth", severity="critical"),
            FusionFinding(source_task="code", category="security", detail="No vulnerability found in auth", severity="info"),
        ]
        conflicts = engine._detect_conflicts(findings)
        assert len(conflicts) >= 1

    def test_no_conflict_same_source(self):
        engine = FusionEngine()
        findings = [
            FusionFinding(source_task="security", category="security", detail="Found vulnerability", severity="critical"),
            FusionFinding(source_task="security", category="security", detail="No vulnerability", severity="info"),
        ]
        conflicts = engine._detect_conflicts(findings)
        assert len(conflicts) == 0

    def test_deduplication(self):
        engine = FusionEngine()
        results = [
            ModelTaskResult(task_id="t1", task_name="arch", model_id="m1",
                            response="Same finding text that should be deduplicated. Very long detail here.",
                            success=True),
            ModelTaskResult(task_id="t2", task_name="arch2", model_id="m2",
                            response="Same finding text that should be deduplicated. Very long detail here.",
                            success=True),
        ]
        result = engine.fuse(results)
        assert result.finding_count == 1

    def test_fusion_result_to_dict(self):
        result = FusionResult(
            summary="test",
            findings=[FusionFinding(source_task="t1", category="arch", summary="finding", severity="info")],
            categories=["arch"],
            sources=["t1 (m1)"],
        )
        d = result.to_dict()
        assert d["summary"] == "test"
        assert result.finding_count == 1
        assert d["finding_count"] == 1
        assert d["has_conflicts"] is False
