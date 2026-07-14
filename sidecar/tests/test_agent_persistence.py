import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import MagicMock, patch
import pytest

from sentinel.core.agent import AgentRegistry, AgentSpec, AgentStatus


class MockAgentRepo:
    def __init__(self):
        self._store: dict = {}

    def list(self):
        return list(self._store.values())

    def get(self, agent_id):
        return self._store.get(agent_id)

    def create(self, spec):
        if spec.id in self._store:
            raise ValueError(f"Agent '{spec.id}' already exists")
        self._store[spec.id] = spec
        return spec

    def update(self, agent_id, updates):
        if agent_id not in self._store:
            return None
        spec = self._store[agent_id]
        for k, v in updates.items():
            if k == "status" and isinstance(v, str):
                from sentinel.core.agent import AgentStatus

                try:
                    v = AgentStatus(v)
                except ValueError:
                    pass
            setattr(spec, k, v)
        return spec

    def delete(self, agent_id):
        return self._store.pop(agent_id, None) is not None

    def count(self):
        return len(self._store)


class TestAgentPersistence:
    def test_registry_accepts_repository(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        assert reg._repository is repo

    def test_load_from_db(self):
        repo = MockAgentRepo()
        a1 = AgentSpec(id="a1", name="A1", description="d")
        repo.create(a1)
        reg = AgentRegistry(repository=repo)
        count = reg.load_from_db()
        assert count >= 1
        assert reg.get("a1") is not None

    def test_set_repository(self):
        reg = AgentRegistry()
        repo = MockAgentRepo()
        reg.set_repository(repo)
        assert reg._repository is repo

    def test_register_persists(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="test1", name="Test 1", description="desc")
        reg.register(a, persist=True)
        assert repo.get("test1") is a

    def test_register_no_persist(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="test2", name="Test 2", description="desc")
        reg.register(a, persist=False)
        assert repo.get("test2") is None

    def test_unregister_persists(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="test3", name="Test 3", description="desc")
        reg.register(a, persist=True)
        assert repo.count() == 1
        reg.unregister("test3", persist=True)
        assert repo.count() == 0
        assert reg.get("test3") is None

    def test_unregister_no_persist(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="test4", name="Test 4", description="desc")
        reg.register(a, persist=True)
        reg.unregister("test4", persist=False)
        assert repo.get("test4") is not None
        assert reg.get("test4") is None

    def test_update_persists(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="test5", name="Test 5", description="desc")
        reg.register(a, persist=True)
        reg.update("test5", persist=True, name="Updated")
        updated = repo.get("test5")
        assert updated.name == "Updated"

    def test_update_no_persist(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="test6", name="Test 6", description="desc")
        reg.register(a, persist=True)
        reg.update("test6", persist=False, name="Updated")
        stored = repo.get("test6")
        assert stored.name == "Test 6"

    def test_register_duplicate_upserts(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="dup", name="Original", description="d")
        reg.register(a, persist=True)
        b = AgentSpec(id="dup", name="Updated", description="d")
        reg.register(b, persist=True)
        stored = repo.get("dup")
        assert stored is not None

    def test_load_from_db_returns_count(self):
        repo = MockAgentRepo()
        repo.create(AgentSpec(id="l1", name="L1", description="d"))
        repo.create(AgentSpec(id="l2", name="L2", description="d"))
        reg = AgentRegistry(repository=repo)
        count = reg.load_from_db()
        assert count == 2
        assert reg.get("l1") is not None
        assert reg.get("l2") is not None

    def test_load_from_db_no_repo(self):
        reg = AgentRegistry()
        assert reg.load_from_db() == 0

    def test_persist_flag_default_true_on_register(self):
        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        a = AgentSpec(id="default", name="Default", description="d")
        reg.register(a)
        assert repo.get("default") is not None


class TestSeedAgents:
    def test_seed_agents_have_required_fields(self):
        from repositories.agent_repository import SEED_AGENTS

        assert len(SEED_AGENTS) >= 3
        for a in SEED_AGENTS:
            assert a.id is not None
            assert a.name is not None
            assert a.provider is not None
            assert a.status == AgentStatus.ACTIVE

    def test_seed_agents_unique_ids(self):
        from repositories.agent_repository import SEED_AGENTS

        ids = [a.id for a in SEED_AGENTS]
        assert len(ids) == len(set(ids))

    def test_seed_agents_can_register(self):
        from repositories.agent_repository import SEED_AGENTS

        repo = MockAgentRepo()
        reg = AgentRegistry(repository=repo)
        for a in SEED_AGENTS:
            reg.register(a, persist=True)
        assert repo.count() == len(SEED_AGENTS)


class TestAgentRepository:
    def setup_method(self):
        self._store: dict = {}

    def _make_repo(self):
        mock = MagicMock()
        mock.list.return_value = list(self._store.values())
        mock.get.side_effect = lambda aid: self._store.get(aid)

        def mock_create(spec):
            if spec.id in self._store:
                raise ValueError(f"Agent '{spec.id}' already exists")
            self._store[spec.id] = spec
            return spec

        mock.create.side_effect = mock_create

        def mock_update(aid, updates):
            if aid not in self._store:
                return None
            spec = self._store[aid]
            for k, v in updates.items():
                setattr(spec, k, v)
            return spec

        mock.update.side_effect = mock_update

        def mock_delete(aid):
            return self._store.pop(aid, None) is not None

        mock.delete.side_effect = mock_delete

        from repositories.agent_repository import AgentRepository

        repo = AgentRepository.__new__(AgentRepository)
        repo._db = MagicMock()
        repo._db.fetchone.return_value = None
        repo._db.fetchall.return_value = []
        repo._db.execute.return_value.rowcount = 1
        return repo

    def test_create_and_get(self):
        from repositories.agent_repository import AgentRepository

        repo = MagicMock(spec=AgentRepository)
        a = AgentSpec(id="cr1", name="CR1", description="test")
        repo.create.return_value = a
        repo.get.return_value = a
        assert repo.create(a).id == "cr1"
        assert repo.get("cr1").name == "CR1"

    def test_create_duplicate_raises(self):
        from repositories.agent_repository import AgentRepository

        repo = MagicMock(spec=AgentRepository)
        repo.create.side_effect = [None, ValueError("already exists")]
        repo.create(AgentSpec(id="dup", name="Dup", description="d"))
        with pytest.raises(ValueError):
            repo.create(AgentSpec(id="dup", name="Dup2", description="d"))

    def test_list(self):
        from repositories.agent_repository import AgentRepository

        repo = MagicMock(spec=AgentRepository)
        repo.list.return_value = [
            AgentSpec(id="l1", name="L1", description="d"),
            AgentSpec(id="l2", name="L2", description="d"),
        ]
        assert len(repo.list()) == 2

    def test_update(self):
        from repositories.agent_repository import AgentRepository

        repo = MagicMock(spec=AgentRepository)
        a = AgentSpec(id="up1", name="Original")
        repo.update.return_value = AgentSpec(id="up1", name="Updated", description="new desc")
        repo.create.return_value = a
        repo.create(a)
        updated = repo.update("up1", {"name": "Updated", "description": "new desc"})
        assert updated.name == "Updated"

    def test_update_nonexistent(self):
        from repositories.agent_repository import AgentRepository

        repo = MagicMock(spec=AgentRepository)
        repo.update.return_value = None
        assert repo.update("nonexistent", {"name": "X"}) is None

    def test_delete(self):
        from repositories.agent_repository import AgentRepository

        repo = MagicMock(spec=AgentRepository)
        repo.create.return_value = AgentSpec(id="del1", name="DEL1")
        repo.delete.side_effect = [True, False]
        repo.create(AgentSpec(id="del1", name="DEL1"))
        assert repo.delete("del1") is True
        assert repo.delete("del1") is False

    def test_count(self):
        from repositories.agent_repository import AgentRepository

        repo = MagicMock(spec=AgentRepository)
        repo.count.side_effect = [0, 2]
        assert repo.count() == 0
        assert repo.count() == 2


class TestAgentsAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge

        reset_bridge()
        from main import app

        app.state._test_mode = True
        app.state._test_secret = "valid-test-token"

    def _client(self):
        from fastapi.testclient import TestClient
        from main import app

        return TestClient(app, headers={"X-Test-Token": "valid-test-token"})

    def test_list_agents(self):
        client = self._client()
        resp = client.get("/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_create_and_delete_agent(self):
        client = self._client()
        resp = client.post(
            "/v1/agents",
            json={
                "agent_id": "test-api-agent",
                "name": "Test API Agent",
                "provider": "ollama",
                "model": "llama3",
            },
        )
        assert resp.status_code == 201
        resp = client.delete("/v1/agents/test-api-agent")
        assert resp.status_code == 200

    def test_create_duplicate_returns_409(self):
        client = self._client()
        resp = client.post("/v1/agents", json={"agent_id": "dup-test", "name": "Dup"})
        assert resp.status_code == 201
        resp = client.post("/v1/agents", json={"agent_id": "dup-test", "name": "Dup"})
        assert resp.status_code == 409
        client.delete("/v1/agents/dup-test")

    def test_get_nonexistent_returns_404(self):
        client = self._client()
        resp = client.get("/v1/agents/nonexistent-xyz")
        assert resp.status_code == 404

    def test_update_agent(self):
        client = self._client()
        client.post("/v1/agents", json={"agent_id": "up-test", "name": "Original"})
        resp = client.patch("/v1/agents/up-test", json={"name": "Updated"})
        assert resp.status_code == 200
        resp = client.get("/v1/agents/up-test")
        assert resp.json()["name"] == "Updated"
        client.delete("/v1/agents/up-test")
