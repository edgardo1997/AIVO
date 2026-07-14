import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from sentinel.tools.app_discovery_tool import AppDiscoveryTool

client = TestClient(app)


class TestAppDiscoveryTool:
    def test_spec_has_correct_id(self):
        tool = AppDiscoveryTool()
        spec = tool.spec()
        assert spec.id == "app.discovery"
        assert spec.category == "system"

    @pytest.mark.asyncio
    async def test_lookup_found(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({"action": "lookup", "name": "python"}, {})
        assert result.success is True
        data = result.data
        assert data["name"] == "python"
        assert data["found"] is True
        assert data["path"] is not None

    @pytest.mark.asyncio
    async def test_lookup_not_found(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({"action": "lookup", "name": "nonexistent_tool_xyz"}, {})
        assert result.success is True
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_lookup_missing_name(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({"action": "lookup"}, {})
        assert result.success is False
        assert "name is required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_list_returns_apps(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({"action": "list", "limit": 10}, {})
        assert result.success is True
        data = result.data
        assert "apps" in data
        assert len(data["apps"]) > 0
        assert data["total"] <= 10

    @pytest.mark.asyncio
    async def test_search_returns_matches(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({"action": "search", "query": "python", "limit": 10}, {})
        assert result.success is True
        data = result.data
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_search_missing_query(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({"action": "search"}, {})
        assert result.success is False
        assert "query is required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_default_action_is_list(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({}, {})
        assert result.success is True
        assert "apps" in result.data

    @pytest.mark.asyncio
    async def test_capabilities_without_registry(self):
        tool = AppDiscoveryTool()
        result = await tool.execute({"action": "capabilities"}, {})
        assert result.success is True
        assert result.data["capabilities"] == []


class TestAppDiscoveryCapabilities:
    def test_capabilities_has_registry_through_api(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "capabilities"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        caps = data["data"]["capabilities"]
        assert len(caps) > 0
        assert any(c["id"] == "app.discovery" for c in caps)
        assert any(c["id"] == "system.cpu" for c in caps)
        assert any(c["id"] == "executor.command" for c in caps)
        first = caps[0]
        assert "risk_level" in first
        assert "tags" in first

    def test_capabilities_count_matches_gateway(self):
        resp_gw = client.get("/api/sentinel/capabilities")
        gw_tools = resp_gw.json()["tools"]
        resp_caps = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "capabilities"},
            },
        )
        caps = resp_caps.json()["data"]["capabilities"]
        cap_ids = {c["id"] for c in caps}
        gw_ids = {t["id"] for t in gw_tools}
        assert cap_ids == gw_ids


class TestAppDiscoveryViaApi:
    def test_app_discovery_tool_registered(self):
        resp = client.get("/api/sentinel/capabilities")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        ids = [t["id"] for t in tools]
        assert "app.discovery" in ids

    def test_v1_execute_lookup(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "lookup", "name": "python"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["name"] == "python"
        assert data["data"]["found"] is True

    def test_v1_execute_list(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "list", "limit": 5},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["apps"]) >= 1

    def test_v1_execute_search(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "search", "query": "python"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_unknown_tool_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.nonexistent",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_v1_execute_dry_run_app_discovery(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "list", "limit": 5},
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        assert data["success"] is True
        assert data["data"]["simulated"] is True
