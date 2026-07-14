import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, AsyncMock
import pytest

from sentinel.core.skill import SkillSpec, SkillResult, SkillRegistry, BUILTIN_SKILLS
from sentinel.core.skill_engine import SkillEngine


class TestSkillSpec:
    def test_to_dict(self):
        s = SkillSpec(id="test.skill", name="Test", description="A test skill", category="test")
        d = s.to_dict()
        assert d["id"] == "test.skill"
        assert d["name"] == "Test"
        assert d["category"] == "test"
        assert d["version"] == "1.0.0"
        assert d["risk_level"] == "low"

    def test_to_dict_with_all_fields(self):
        s = SkillSpec(
            id="full.skill", name="Full", description="Full skill", category="code",
            tools=["tool.a", "tool.b"], system_prompt="Do stuff",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"y": {"type": "integer"}}},
            preconditions=["pre"], postconditions=["post"],
            risk_level="high", requires_confirmation=True, version="2.0.0",
            tags=["tag1", "tag2"],
        )
        d = s.to_dict()
        assert d["tools"] == ["tool.a", "tool.b"]
        assert d["risk_level"] == "high"
        assert d["requires_confirmation"] is True
        assert d["version"] == "2.0.0"
        assert d["tags"] == ["tag1", "tag2"]


class TestSkillResult:
    def test_to_dict_success(self):
        r = SkillResult(skill_id="s1", success=True, data={"result": 42}, plan_summary="done")
        d = r.to_dict()
        assert d["skill_id"] == "s1"
        assert d["success"] is True
        assert d["data"] == {"result": 42}

    def test_to_dict_failure(self):
        r = SkillResult(skill_id="s1", success=False, error="something broke")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "something broke"


class TestSkillRegistry:
    def test_register_and_get(self):
        reg = SkillRegistry()
        s = SkillSpec(id="test.skill", name="Test", description="desc", category="cat")
        reg.register(s)
        assert reg.get("test.skill") is s

    def test_register_duplicate_raises(self):
        reg = SkillRegistry()
        s = SkillSpec(id="dup", name="Dup", description="d", category="c")
        reg.register(s)
        with pytest.raises(ValueError):
            reg.register(SkillSpec(id="dup", name="Dup2", description="d", category="c"))

    def test_unregister(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="s1", name="S1", description="d", category="c"))
        assert reg.unregister("s1") is not None
        assert reg.get("s1") is None

    def test_unregister_nonexistent(self):
        reg = SkillRegistry()
        assert reg.unregister("nonexistent") is None

    def test_list_all(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="a", name="A", description="d", category="cat1"))
        reg.register(SkillSpec(id="b", name="B", description="d", category="cat2"))
        assert len(reg.list()) == 2

    def test_list_by_category(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="a", name="A", description="d", category="code"))
        reg.register(SkillSpec(id="b", name="B", description="d", category="system"))
        assert len(reg.list(category="code")) == 1
        assert len(reg.list(category="system")) == 1

    def test_find_by_name(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="code.review", name="Code Review", description="Review code", category="code"))
        results = reg.find("review")
        assert len(results) == 1
        assert results[0].id == "code.review"

    def test_find_by_tag(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="test.skill", name="Test", description="desc", category="c", tags=["analysis"]))
        results = reg.find("analysis")
        assert len(results) == 1

    def test_find_no_match(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="s1", name="S1", description="d", category="c"))
        assert reg.find("nonexistent") == []

    def test_find_for_task_scores_correctly(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="code.review", name="Code Review", description="Review code", category="code", tags=["code", "quality"]))
        reg.register(SkillSpec(id="system.diag", name="System Diagnosis", description="Diagnose system", category="system", tags=["system", "health"]))
        results = reg.find_for_task("review the code quality")
        assert len(results) >= 1
        assert results[0].id == "code.review"

    def test_load_builtins(self):
        reg = SkillRegistry()
        count = reg.load_builtins()
        assert count == len(BUILTIN_SKILLS)
        assert reg.get("code.review") is not None
        assert reg.get("system.diagnose") is not None
        assert reg.get("files.organize") is not None
        assert reg.get("research.summarize") is not None
        assert reg.get("data.analyze") is not None

    def test_load_builtins_idempotent(self):
        reg = SkillRegistry()
        reg.load_builtins()
        count = reg.load_builtins()
        assert count == 0

    def test_to_dict(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="s1", name="S1", description="d", category="c"))
        d = reg.to_dict()
        assert len(d) == 1
        assert d[0]["id"] == "s1"


class TestSkillEngine:
    @pytest.mark.asyncio
    async def test_execute_skill_not_found(self):
        reg = SkillRegistry()
        engine = SkillEngine(registry=reg)
        result = await engine.execute("nonexistent", {})
        assert result.success is False
        assert "not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_missing_required(self):
        reg = SkillRegistry()
        s = SkillSpec(id="test.req", name="Test Required", description="d", category="c",
                       input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]})
        reg.register(s)
        engine = SkillEngine(registry=reg)
        result = await engine.execute("test.req", {})
        assert result.success is False
        assert "Missing required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_enum(self):
        reg = SkillRegistry()
        s = SkillSpec(id="test.enum", name="Test Enum", description="d", category="c",
                       input_schema={"type": "object", "properties": {"mode": {"type": "string", "enum": ["a", "b"]}}, "required": ["mode"]})
        reg.register(s)
        engine = SkillEngine(registry=reg)
        result = await engine.execute("test.enum", {"mode": "c"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_with_gateway(self):
        reg = SkillRegistry()
        s = SkillSpec(id="test.exec", name="Test Exec", description="d", category="c",
                       tools=["test.tool"])
        reg.register(s)
        gw = MagicMock()
        gw.get_spec.return_value = MagicMock()
        gw.execute = AsyncMock()
        gw.execute.return_value.success = True
        gw.execute.return_value.data = {"done": True}
        gw.execute.return_value.error = None
        gw.execute.return_value.duration_ms = 10.0
        engine = SkillEngine(registry=reg, tool_gateway=gw)
        result = await engine.execute("test.exec", {"x": 1})
        assert result.success is True
        gw.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_step_failure_stops(self):
        reg = SkillRegistry()
        s = SkillSpec(id="test.fail", name="Test Fail", description="d", category="c",
                       tools=["tool.a", "tool.b"])
        reg.register(s)
        gw = MagicMock()
        gw.get_spec.return_value = MagicMock()
        gw.execute = AsyncMock()
        gw.execute.return_value.success = False
        gw.execute.return_value.error = "step failed"
        gw.execute.return_value.duration_ms = 5.0
        engine = SkillEngine(registry=reg, tool_gateway=gw)
        result = await engine.execute("test.fail", {})
        assert result.success is False
        assert gw.execute.call_count == 1

    def test_find_skills(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="code.review", name="Code Review", description="Review code", category="code"))
        engine = SkillEngine(registry=reg)
        results = engine.find_skills("review the code")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_suggest_finds_skills(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="code.review", name="Code Review", description="Review code", category="code", tags=["code"]))
        engine = SkillEngine(registry=reg)
        result = await engine.suggest("review the code")
        assert result["matched"] is True
        assert len(result["skills"]) >= 1

    @pytest.mark.asyncio
    async def test_suggest_no_match(self):
        reg = SkillRegistry()
        engine = SkillEngine(registry=reg)
        result = await engine.suggest("xyznonexistent")
        assert result["matched"] is False

    def test_to_dict(self):
        reg = SkillRegistry()
        reg.register(SkillSpec(id="s1", name="S1", description="d", category="c"))
        engine = SkillEngine(registry=reg)
        d = engine.to_dict()
        assert d["total_skills"] == 1
        assert len(d["skills"]) == 1

    def test_validate_params_optional_not_required(self):
        reg = SkillRegistry()
        s = SkillSpec(id="test.opt", name="Test Opt", description="d", category="c",
                       input_schema={"type": "object", "properties": {"x": {"type": "string"}}})
        engine = SkillEngine(registry=reg)
        err = engine._validate_params(s, {"y": 1})
        assert err is None


class TestSkillsAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge
        reset_bridge()

    def test_list_skills(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert "skills" in data
        assert data["enabled"] is True

    def test_find_skills(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/skills/find?q=code")
        assert resp.status_code == 200

    def test_find_skills_empty_query(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/skills/find?q=")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_suggest_skill(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/skills/suggest", json={"task": "organize files"})
        assert resp.status_code == 200

    def test_suggest_skill_no_task(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/skills/suggest", json={})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_execute_skill_no_skill_id(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/skills/execute", json={"params": {}})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
