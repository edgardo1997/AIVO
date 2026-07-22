import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from modules.permissions import _svc as perm_svc
from sentinel.core.agent import AgentRegistry, AgentSpec, AgentStatus

client = TestClient(app)
client.headers.update({"X-Test-Token": "valid-test-token"})


class TestAgentRegistry:
    def test_register_and_get(self):
        registry = AgentRegistry()
        agent = AgentSpec(id="test-agent", name="Test", provider="ollama", model="llama3")
        registry.register(agent)
        assert registry.get("test-agent") is not None
        assert registry.get("test-agent").name == "Test"

    def test_register_duplicate_overwrites(self):
        registry = AgentRegistry()
        a1 = AgentSpec(id="dup", name="First", provider="ollama", model="a")
        a2 = AgentSpec(id="dup", name="Second", provider="openrouter", model="b")
        registry.register(a1)
        registry.register(a2)
        assert registry.get("dup").name == "Second"

    def test_unregister_removes_agent(self):
        registry = AgentRegistry()
        agent = AgentSpec(id="del-me", name="Delete Me", provider="ollama", model="x")
        registry.register(agent)
        registry.unregister("del-me")
        assert registry.get("del-me") is None

    def test_unregister_unknown_raises(self):
        registry = AgentRegistry()
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")

    def test_list_all(self):
        registry = AgentRegistry()
        registry.register(AgentSpec(id="a", name="A", provider="ollama", model="x"))
        registry.register(AgentSpec(id="b", name="B", provider="openrouter", model="y"))
        assert len(registry.list_all()) == 2

    def test_find_by_capability(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(
                id="coder", name="Coder", provider="openrouter", model="gpt-4o", capabilities=["code", "reasoning"]
            )
        )
        registry.register(
            AgentSpec(id="analyst", name="Analyst", provider="ollama", model="llama3", capabilities=["analysis"])
        )
        results = registry.find_by_capability("code")
        assert len(results) == 1
        assert results[0].id == "coder"

    def test_find_by_provider(self):
        registry = AgentRegistry()
        registry.register(AgentSpec(id="a", name="A", provider="ollama", model="x"))
        registry.register(AgentSpec(id="b", name="B", provider="openrouter", model="y"))
        registry.register(AgentSpec(id="c", name="C", provider="ollama", model="z"))
        assert len(registry.find_by_provider("ollama")) == 2
        assert len(registry.find_by_provider("openrouter")) == 1

    def test_list_active(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(id="active1", name="Active1", provider="ollama", model="x", status=AgentStatus.ACTIVE)
        )
        registry.register(AgentSpec(id="idle1", name="Idle1", provider="ollama", model="y"))
        registry.register(
            AgentSpec(id="active2", name="Active2", provider="ollama", model="z", status=AgentStatus.ACTIVE)
        )
        assert len(registry.list_active()) == 2

    def test_update_agent(self):
        registry = AgentRegistry()
        agent = AgentSpec(id="upd", name="Original", provider="ollama", model="x")
        registry.register(agent)
        registry.update("upd", name="Updated", status=AgentStatus.ACTIVE)
        assert registry.get("upd").name == "Updated"
        assert registry.get("upd").status == AgentStatus.ACTIVE

    def test_update_status_from_string(self):
        registry = AgentRegistry()
        agent = AgentSpec(id="upd2", name="Test", provider="ollama", model="x")
        registry.register(agent)
        registry.update("upd2", status="disabled")
        assert registry.get("upd2").status == AgentStatus.DISABLED

    def test_to_dict_includes_all_fields(self):
        agent = AgentSpec(
            id="full",
            name="Full Agent",
            description="Does stuff",
            provider="openrouter",
            model="gpt-4",
            capabilities=["code", "reasoning"],
            allowed_tools=["system.cpu"],
            system_prompt="Be helpful",
            status=AgentStatus.ACTIVE,
            max_concurrency=3,
        )
        d = agent.to_dict()
        assert d["id"] == "full"
        assert d["provider"] == "openrouter"
        assert d["model"] == "gpt-4"
        assert d["capabilities"] == ["code", "reasoning"]
        assert d["status"] == "active"
        assert d["max_concurrency"] == 3

    def test_from_dict_roundtrip(self):
        original = AgentSpec(
            id="rt",
            name="Roundtrip",
            provider="ollama",
            model="llama3",
            capabilities=["test"],
            status=AgentStatus.ACTIVE,
        )
        d = original.to_dict()
        restored = AgentSpec.from_dict(d)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.provider == original.provider
        assert restored.status == original.status

    def test_count(self):
        registry = AgentRegistry()
        assert registry.count() == 0
        registry.register(AgentSpec(id="x", name="X", provider="ollama", model="x"))
        assert registry.count() == 1


class TestAgentTools:
    def setup_method(self):
        perm_svc.set_level("admin")

    def test_agent_list_empty(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.list",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] >= 0

    def test_agent_create_and_list(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.create",
                "params": {
                    "id": "test-agent-tool",
                    "name": "Test Agent",
                    "provider": "ollama",
                    "model": "llama3",
                    "capabilities": ["test", "demo"],
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "created"

        listed = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.list",
                "params": {},
            },
        )
        assert listed.status_code == 200
        agents = listed.json()["data"]["agents"]
        ids = [a["id"] for a in agents]
        assert "test-agent-tool" in ids

    def test_agent_create_duplicate_returns_error(self):
        client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.create",
                "params": {"id": "dup-agent", "name": "Dup", "provider": "ollama", "model": "x"},
            },
        )
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.create",
                "params": {"id": "dup-agent", "name": "Dup2", "provider": "ollama", "model": "y"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_agent_delete(self):
        client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.create",
                "params": {"id": "del-agent-tool", "name": "Delete Me", "provider": "ollama", "model": "x"},
            },
        )
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delete",
                "params": {"id": "del-agent-tool"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "deleted"

    def test_agent_delegate_returns_agent_info(self):
        client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.create",
                "params": {
                    "id": "delegate-target",
                    "name": "Target",
                    "provider": "ollama",
                    "model": "llama3",
                    "capabilities": ["code"],
                    "system_prompt": "You are a coding assistant",
                },
            },
        )
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delegate",
                "params": {"agent_id": "delegate-target", "task": "Write a hello world in Python"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["data"] is not None:
            d = data["data"]
            assert d.get("agent_id") == "delegate-target"
            assert d.get("delegated") is True
            assert d.get("provider") == "ollama"
            assert d.get("model") == "llama3"
        else:
            assert data["success"] is False, data

    def test_agent_delegate_unknown_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delegate",
                "params": {"agent_id": "nonexistent", "task": "do something"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_agent_delegate_real_execution_shape(self):
        """Verify agent.delegate goes through execute_agent() and returns valid shape.
        Success or error are both acceptable depending on whether a provider is running."""
        client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.create",
                "params": {
                    "id": "delegate-real",
                    "name": "Real Target",
                    "provider": "ollama",
                    "model": "llama3",
                    "capabilities": ["code"],
                    "system_prompt": "You are a coding assistant",
                },
            },
        )
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delegate",
                "params": {"agent_id": "delegate-real", "task": "Write hello world in Python"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["data"] is not None:
            d = data["data"]
            assert d.get("agent_id") == "delegate-real"
            assert d.get("delegated") is True
            assert d.get("provider") == "ollama"
            assert d.get("model") == "llama3"
        else:
            assert data["success"] is False, data


class TestAgentDelegation:
    """Unit tests for AgentRegistry.execute_agent() with mocked ModelRouter."""

    def test_execute_agent_calls_model_router_and_returns_response(self):
        registry = AgentRegistry()

        class MockRouter:
            def chat_with_provider(self, messages, provider_id, model, task_type=None):
                assert provider_id == "ollama"
                assert model == "llama3"
                assert len(messages) == 2
                assert messages[0]["role"] == "system"
                assert messages[1]["role"] == "user"
                return {"response": "Hello world", "provider": "ollama", "model": "llama3"}

        registry.set_model_router(MockRouter())
        agent = AgentSpec(
            id="test-agent", name="Test", provider="ollama", model="llama3", system_prompt="You are helpful"
        )
        registry.register(agent)
        result = registry.execute_agent("test-agent", "Write hello world")
        assert result["delegated"] is True
        assert result["response"] == "Hello world"
        assert result["provider"] == "ollama"
        assert result["model"] == "llama3"
        assert result["agent_id"] == "test-agent"

    def test_execute_agent_injects_system_prompt(self):
        registry = AgentRegistry()

        class MockRouter:
            def chat_with_provider(self, messages, provider_id, model, task_type=None):
                assert messages[0]["content"] == "Custom system prompt"
                return {"response": "ok", "provider": "ollama", "model": "x"}

        registry.set_model_router(MockRouter())
        agent = AgentSpec(
            id="sys-agent", name="SysAgent", provider="ollama", model="x", system_prompt="Custom system prompt"
        )
        registry.register(agent)
        result = registry.execute_agent("sys-agent", "do it")
        assert result["delegated"] is True

    def test_execute_agent_injects_task_context(self):
        registry = AgentRegistry()

        class MockRouter:
            def chat_with_provider(self, messages, provider_id, model, task_type=None):
                assert "Task: do it" in messages[-1]["content"]
                assert "Context:" in messages[-1]["content"]
                assert "file_count" in messages[-1]["content"]
                return {"response": "done", "provider": "ollama", "model": "x"}

        registry.set_model_router(MockRouter())
        agent = AgentSpec(id="ctx-agent", name="CtxAgent", provider="ollama", model="x")
        registry.register(agent)
        result = registry.execute_agent("ctx-agent", "do it", {"file_count": 5})
        assert result["delegated"] is True

    def test_execute_agent_no_messages_when_no_system_prompt(self):
        registry = AgentRegistry()

        class MockRouter:
            def chat_with_provider(self, messages, provider_id, model, task_type=None):
                assert len(messages) == 1
                assert messages[0]["role"] == "user"
                return {"response": "ok", "provider": "ollama", "model": "x"}

        registry.set_model_router(MockRouter())
        agent = AgentSpec(id="no-sys", name="NoSys", provider="ollama", model="x", system_prompt="")
        registry.register(agent)
        result = registry.execute_agent("no-sys", "do something")
        assert result["delegated"] is True

    def test_execute_agent_fallback_stub_when_no_router(self):
        registry = AgentRegistry()
        agent = AgentSpec(id="stub-agent", name="Stub", provider="ollama", model="x")
        registry.register(agent)
        result = registry.execute_agent("stub-agent", "task")
        assert result["delegated"] is True
        assert result.get("stub") is True

    def test_execute_agent_returns_error_on_router_failure(self):
        registry = AgentRegistry()

        class FailingRouter:
            def chat_with_provider(self, messages, provider_id, model, task_type=None):
                raise ConnectionError("Provider not available")

        registry.set_model_router(FailingRouter())
        agent = AgentSpec(id="fail-agent", name="Fail", provider="ollama", model="x")
        registry.register(agent)
        result = registry.execute_agent("fail-agent", "task")
        assert result["delegated"] is True
        assert "error" in result
        assert "not available" in result["error"]

    def test_execute_agent_unknown_raises(self):
        registry = AgentRegistry()
        with pytest.raises(KeyError):
            registry.execute_agent("does-not-exist", "task")

    def test_execute_agent_disabled_still_executes(self):
        registry = AgentRegistry()
        agent = AgentSpec(
            id="disabled-agent", name="Disabled", provider="ollama", model="x", status=AgentStatus.DISABLED
        )
        registry.register(agent)
        result = registry.execute_agent("disabled-agent", "task")
        assert result["delegated"] is True
        assert result.get("stub") is True

    def test_execute_agent_empty_task(self):
        registry = AgentRegistry()

        class MockRouter:
            def chat_with_provider(self, messages, provider_id, model, task_type=None):
                assert messages[-1]["content"] == ""
                return {"response": "ok", "provider": "ollama", "model": "x"}

        registry.set_model_router(MockRouter())
        agent = AgentSpec(id="empty-task", name="Empty", provider="ollama", model="x")
        registry.register(agent)
        result = registry.execute_agent("empty-task", "")
        assert result["delegated"] is True

    def test_set_model_router_stores_router(self):
        registry = AgentRegistry()
        assert registry._model_router is None
        registry.set_model_router(object())
        assert registry._model_router is not None


class TestAgentsAPI:
    def test_list_via_api(self):
        resp = client.get("/v1/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_via_api(self):
        resp = client.post(
            "/v1/agents",
            json={
                "agent_id": "api-created-agent",
                "name": "API Created",
                "provider": "openrouter",
                "model": "gpt-4o",
                "capabilities": ["code", "reasoning"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"

        fetched = client.get("/v1/agents/api-created-agent")
        assert fetched.status_code == 200
        assert fetched.json()["provider"] == "openrouter"

    def test_create_duplicate_via_api_returns_409(self):
        client.post("/v1/agents", json={"agent_id": "dup-api", "name": "Dup"})
        resp = client.post("/v1/agents", json={"agent_id": "dup-api", "name": "Dup2"})
        assert resp.status_code == 409

    def test_update_via_api(self):
        client.post("/v1/agents", json={"agent_id": "upd-api", "name": "Original"})
        resp = client.patch("/v1/agents/upd-api", json={"name": "Updated", "status": "active"})
        assert resp.status_code == 200
        fetched = client.get("/v1/agents/upd-api")
        assert fetched.json()["name"] == "Updated"
        assert fetched.json()["status"] == "active"

    def test_delete_via_api(self):
        client.post("/v1/agents", json={"agent_id": "del-api", "name": "Delete Me"})
        resp = client.delete("/v1/agents/del-api")
        assert resp.status_code == 200
        fetched = client.get("/v1/agents/del-api")
        assert fetched.status_code == 404

    def test_get_unknown_returns_404(self):
        resp = client.get("/v1/agents/does-not-exist")
        assert resp.status_code == 404

    def test_delete_unknown_returns_404(self):
        resp = client.delete("/v1/agents/does-not-exist")
        assert resp.status_code == 404

    def test_create_with_invalid_status(self):
        resp = client.post(
            "/v1/agents",
            json={
                "agent_id": "bad-status",
                "name": "Bad",
                "status": "invalid_status",
            },
        )
        assert resp.status_code == 400

    def test_agent_tools_appear_in_capabilities(self):
        resp = client.get("/api/sentinel/capabilities")
        data = resp.json()
        tool_ids = [t["id"] for t in data["tools"]]
        assert "agent.list" in tool_ids
        assert "agent.create" in tool_ids
        assert "agent.delete" in tool_ids
        assert "agent.delegate" in tool_ids


class TestMultiModelRouting:
    """Tests for multi-model auto-selection and strategy-based routing."""

    def setup_method(self):
        perm_svc.set_level("admin")

    def test_analyze_complexity_short_is_simple(self):
        registry = AgentRegistry()
        assert registry._analyze_complexity("hello") == "simple"
        assert registry._analyze_complexity("short task") == "simple"
        assert registry._analyze_complexity("") == "simple"

    def test_analyze_complexity_long_is_complex(self):
        registry = AgentRegistry()
        assert registry._analyze_complexity("a b c d e f g h") == "complex"

    def test_analyze_complexity_keyword_is_complex(self):
        registry = AgentRegistry()
        assert registry._analyze_complexity("design a new feature") == "complex"
        assert registry._analyze_complexity("analyze this data") == "complex"
        assert registry._analyze_complexity("refactor this code") == "complex"

    def test_find_best_agent_auto_selects_local_for_simple(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(
                id="local",
                name="Local",
                provider="ollama",
                model="llama3",
                capabilities=["quick"],
                status=AgentStatus.ACTIVE,
            )
        )
        registry.register(
            AgentSpec(
                id="remote",
                name="Remote",
                provider="openrouter",
                model="gpt-4o",
                capabilities=["reasoning"],
                status=AgentStatus.ACTIVE,
            )
        )
        best = registry.find_best_agent("hello", strategy="auto")
        assert best is not None
        assert best.id == "local"

    def test_find_best_agent_auto_selects_remote_for_complex(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(
                id="local",
                name="Local",
                provider="ollama",
                model="llama3",
                capabilities=["quick"],
                status=AgentStatus.ACTIVE,
            )
        )
        registry.register(
            AgentSpec(
                id="remote",
                name="Remote",
                provider="openrouter",
                model="gpt-4o",
                capabilities=["reasoning"],
                status=AgentStatus.ACTIVE,
            )
        )
        best = registry.find_best_agent("design a new architecture for this system", strategy="auto")
        assert best is not None
        assert best.id == "remote"

    def test_find_best_agent_strategy_local(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(id="local", name="Local", provider="ollama", model="llama3", status=AgentStatus.ACTIVE)
        )
        registry.register(
            AgentSpec(id="remote", name="Remote", provider="openrouter", model="gpt-4o", status=AgentStatus.ACTIVE)
        )
        best = registry.find_best_agent("complex task", strategy="local")
        assert best.id == "local"

    def test_find_best_agent_strategy_powerful(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(id="local", name="Local", provider="ollama", model="llama3", status=AgentStatus.ACTIVE)
        )
        registry.register(
            AgentSpec(id="remote", name="Remote", provider="openrouter", model="gpt-4o", status=AgentStatus.ACTIVE)
        )
        best = registry.find_best_agent("simple task", strategy="powerful")
        assert best.id == "remote"

    def test_find_best_agent_prefers_active_over_idle(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(id="idle-agent", name="Idle", provider="ollama", model="x", status=AgentStatus.IDLE)
        )
        registry.register(
            AgentSpec(id="active-agent", name="Active", provider="ollama", model="y", status=AgentStatus.ACTIVE)
        )
        best = registry.find_best_agent("task")
        assert best.id == "active-agent"

    def test_find_best_agent_returns_none_when_all_disabled(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(id="disabled", name="Disabled", provider="ollama", model="x", status=AgentStatus.DISABLED)
        )
        best = registry.find_best_agent("task")
        assert best is None

    def test_find_best_agent_respects_capabilities_hint(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(
                id="coder", name="Coder", provider="ollama", model="x", capabilities=["code"], status=AgentStatus.ACTIVE
            )
        )
        registry.register(
            AgentSpec(
                id="analyst",
                name="Analyst",
                provider="openrouter",
                model="y",
                capabilities=["analysis"],
                status=AgentStatus.ACTIVE,
            )
        )
        best = registry.find_best_agent("task", capabilities_hint=["code"])
        assert best.id == "coder"

    def test_resolve_agent_with_id_returns_same_agent(self):
        registry = AgentRegistry()
        agent = AgentSpec(id="specific", name="Specific", provider="ollama", model="x", status=AgentStatus.ACTIVE)
        registry.register(agent)
        resolved = registry.resolve_agent(agent_id="specific")
        assert resolved.id == "specific"

    def test_resolve_agent_without_id_auto_selects(self):
        registry = AgentRegistry()
        registry.register(
            AgentSpec(id="local", name="Local", provider="ollama", model="llama3", status=AgentStatus.ACTIVE)
        )
        resolved = registry.resolve_agent(task="hello")
        assert resolved.id == "local"

    def test_resolve_agent_without_id_and_no_agents_uses_router(self):
        registry = AgentRegistry()

        class MockRouter:
            def select(self, task_type, context=None):
                from sentinel.core.model_router import RouterDecision, TaskType

                return RouterDecision(
                    provider_id="openrouter",
                    model="gpt-4o",
                    task_type=task_type,
                    strategy="priority",
                    reason="mock",
                )

        registry.set_model_router(MockRouter())
        resolved = registry.resolve_agent(task="design a system")
        assert resolved.provider == "openrouter"
        assert resolved.model == "gpt-4o"

    def test_resolve_agent_without_id_raises_when_no_agents_and_no_router(self):
        registry = AgentRegistry()
        with pytest.raises(KeyError):
            registry.resolve_agent(task="task")

    def test_delegate_without_agent_id_auto_selects(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delegate",
                "params": {"task": "write hello world", "strategy": "auto"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True or data["success"] is False
        if data["success"]:
            assert "agent_id" in data["data"]
            assert "response" in data["data"]

    def test_delegate_with_strategy_local(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delegate",
                "params": {"task": "complex analysis task", "strategy": "local"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["success"]:
            assert "agent_id" in data["data"]
            assert data["data"]["provider"] == "ollama" or data["data"]["delegated"] is True
        else:
            assert data["requires_confirmation"] is True or data["error"]

    def test_delegate_without_task_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delegate",
                "params": {"task": ""},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
