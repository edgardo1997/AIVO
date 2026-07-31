import pytest
from sentinel.intelligence.task_planner import TaskPlanner, TaskComplexity, PlannedTask, classify_request


class TestTaskPlanner:
    def test_simple_request_creates_single_task(self):
        planner = TaskPlanner()
        plan = planner.plan("Hello")
        assert len(plan.tasks) == 1
        assert plan.tasks[0].complexity == TaskComplexity.SIMPLE

    def test_complex_request_creates_multi_task(self):
        planner = TaskPlanner()
        plan = planner.plan("Analyze this software architecture for security vulnerabilities and performance bottlenecks")
        assert len(plan.tasks) >= 2

    def test_security_request_detects_security_domain(self):
        planner = TaskPlanner()
        plan = planner.plan("Review the authentication system for vulnerabilities and analyze the access control mechanisms for potential threats")
        task_names = [t.name for t in plan.tasks]
        assert any("vulnerability" in n or "access" in n for n in task_names)

    def test_performance_request_detects_performance_domain(self):
        planner = TaskPlanner()
        plan = planner.plan("Find performance bottlenecks in the database queries and suggest optimization strategies for the slow queries")
        task_names = [t.name for t in plan.tasks]
        assert any("bottleneck" in n or "optimization" in n for n in task_names)

    def test_classify_request_detects_domains(self):
        result = classify_request("Check security and performance of the API")
        assert "security" in result["domains"]
        assert "performance" in result["domains"]

    def test_classify_request_complexity(self):
        simple = classify_request("Hi")
        assert simple["complexity"] == TaskComplexity.SIMPLE
        moderate = classify_request("This is a moderately complex request about architecture and design patterns for software systems")
        assert moderate["complexity"] == TaskComplexity.MODERATE
        complex_req = classify_request("Analyze this software architecture for security vulnerabilities and performance bottlenecks. Review the code quality, testing coverage, and deployment pipeline. Also check the data schema and user experience considerations for the new platform deployment strategy.")
        assert complex_req["complexity"] == TaskComplexity.COMPLEX

    def test_add_custom_rule(self):
        planner = TaskPlanner()
        planner.add_rule("custom", [{"name": "custom_analysis", "capabilities": ["reasoning"], "description": "Custom analysis"}])
        plan = planner.plan("Perform custom analysis on the system")
        # "custom" is not a keyword, so it won't auto-detect. We need to test rule structure directly.
        assert "custom" in planner._rules
        assert len(planner._rules["custom"]) == 1

    def test_general_domain_fallback(self):
        planner = TaskPlanner()
        plan = planner.plan("Tell me about the weather")
        assert len(plan.tasks) == 1
        assert plan.tasks[0].name == "analysis"

    def test_task_plan_serialization(self):
        planner = TaskPlanner()
        plan = planner.plan("Analyze security")
        d = plan.to_dict()
        assert "original_request" in d
        assert "tasks" in d
        assert "execution_strategy" in d
        assert len(d["tasks"]) >= 1

    def test_planned_task_to_dict(self):
        task = PlannedTask(task_id="t1", name="test", objective="do something", required_capabilities=["reasoning"], priority=5, complexity=TaskComplexity.MODERATE)
        d = task.to_dict()
        assert d["task_id"] == "t1"
        assert d["complexity"] == "moderate"
