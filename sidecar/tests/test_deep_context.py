"""Tests for the DeepContextEngine."""

import threading

import pytest

from sentinel.core.deep_context import DeepContextEngine


@pytest.mark.asyncio
async def test_collect_minimal():
    ctx = DeepContextEngine()
    result = await ctx.collect()
    assert "timestamp" in result
    assert "system_summary" in result


@pytest.mark.asyncio
async def test_collect_with_all_sources():
    test_apps = [{"name": "TestApp", "id": "test.app"}]
    test_fleet = {"devices": [{"id": "device-1"}]}
    test_goals = [{"id": "goal-1", "name": "Test Goal"}]
    test_caps = [{"id": "system.info"}, {"id": "filesystem.read"}]
    test_tools = ["system.info", "filesystem.read"]
    test_hardware = {"ram_total_gb": 16.0, "gpu_available": False, "confidence": 0.9}

    ctx = DeepContextEngine(
        app_discovery_fn=lambda: test_apps,
        fleet_status_fn=lambda: test_fleet,
        get_goals_fn=lambda: test_goals,
        get_permission_level_fn=lambda: "admin",
        get_capabilities_fn=lambda: test_caps,
        get_connected_tools_fn=lambda: test_tools,
        get_hardware_profile_fn=lambda: test_hardware,
    )
    result = await ctx.collect()
    assert result["installed_apps_count"] == 1
    assert result["fleet_devices_count"] == 1
    assert result["active_goals_count"] == 1
    assert result["permission_level"] == "admin"
    assert result["capabilities_count"] == 2
    assert result["connected_tools_count"] == 2
    assert result["hardware"] == test_hardware


@pytest.mark.asyncio
async def test_host_discovery_sources_run_off_event_loop():
    event_loop_thread = threading.get_ident()
    worker_threads = []

    def applications():
        worker_threads.append(threading.get_ident())
        return []

    def hardware():
        worker_threads.append(threading.get_ident())
        return {"confidence": 1.0}

    await DeepContextEngine(
        app_discovery_fn=applications,
        get_hardware_profile_fn=hardware,
    ).collect()

    assert len(worker_threads) == 2
    assert all(thread_id != event_loop_thread for thread_id in worker_threads)


@pytest.mark.asyncio
async def test_collect_with_failing_sources():
    """Should not crash when callables raise exceptions."""

    def failing():
        raise RuntimeError("fail")

    ctx = DeepContextEngine(
        app_discovery_fn=failing,
        fleet_status_fn=failing,
        get_goals_fn=failing,
    )
    result = await ctx.collect()
    assert result.get("installed_apps_count", 0) == 0
    assert result.get("fleet_devices_count", 0) == 0
    assert result.get("active_goals_count", 0) == 0


@pytest.mark.asyncio
async def test_collect_no_sources():
    ctx = DeepContextEngine(
        app_discovery_fn=None,
        fleet_status_fn=None,
        get_goals_fn=None,
        get_permission_level_fn=None,
        get_capabilities_fn=None,
        get_connected_tools_fn=None,
    )
    result = await ctx.collect()
    assert "timestamp" in result
    assert "system_summary" in result
    assert "installed_apps" not in result
    assert "fleet" not in result
    assert "active_goals" not in result
    assert "permission_level" not in result
    assert "available_capabilities" not in result
    assert "connected_tools" not in result


@pytest.mark.asyncio
async def test_collect_fleet_as_list():
    ctx = DeepContextEngine(
        fleet_status_fn=lambda: [{"id": "d1"}, {"id": "d2"}],
    )
    result = await ctx.collect()
    assert "fleet" in result
    assert result["fleet"] == [{"id": "d1"}, {"id": "d2"}]
    assert "fleet_devices_count" not in result


@pytest.mark.asyncio
async def test_collect_fleet_with_peers_key():
    ctx = DeepContextEngine(
        fleet_status_fn=lambda: {"peers": [{"id": "p1"}, {"id": "p2"}]},
    )
    result = await ctx.collect()
    assert result["fleet_devices_count"] == 2


@pytest.mark.asyncio
async def test_collect_empty_lists():
    ctx = DeepContextEngine(
        app_discovery_fn=lambda: [],
        fleet_status_fn=lambda: {"devices": []},
        get_goals_fn=lambda: [],
        get_capabilities_fn=lambda: [],
        get_connected_tools_fn=lambda: [],
    )
    result = await ctx.collect()
    assert result["installed_apps_count"] == 0
    assert result["fleet_devices_count"] == 0
    assert result["active_goals_count"] == 0
    assert result["capabilities_count"] == 0
    assert result["connected_tools_count"] == 0


@pytest.mark.asyncio
async def test_collect_permission_defaults_to_confirm_on_missing_fn():
    ctx = DeepContextEngine(get_permission_level_fn=None)
    result = await ctx.collect()
    assert "permission_level" not in result


@pytest.mark.asyncio
async def test_collect_permission_defaults_to_confirm_on_failure():
    def fail():
        raise RuntimeError("fail")

    ctx = DeepContextEngine(get_permission_level_fn=fail)
    result = await ctx.collect()
    assert result["permission_level"] == "confirm"


@pytest.mark.asyncio
async def test_collect_system_context_failure():
    engine = DeepContextEngine()
    engine._system.collect_fail = True

    async def fail_collect(*args, **kwargs):
        raise RuntimeError("system failure")

    engine._system.collect = fail_collect
    result = await engine.collect()
    assert "system_summary" in result
    assert result["system_summary"] == {}


@pytest.mark.asyncio
async def test_collect_apps_only():
    ctx = DeepContextEngine(
        app_discovery_fn=lambda: [{"name": "App1"}],
        fleet_status_fn=None,
        get_goals_fn=None,
        get_permission_level_fn=None,
        get_capabilities_fn=None,
        get_connected_tools_fn=None,
    )
    result = await ctx.collect()
    assert result["installed_apps_count"] == 1
    assert "fleet" not in result
    assert "active_goals" not in result
    assert "permission_level" not in result
    assert "available_capabilities" not in result
    assert "connected_tools" not in result


@pytest.mark.asyncio
async def test_summary():
    ctx = DeepContextEngine()
    result = await ctx.collect()
    summary = ctx.summary(result)
    assert isinstance(summary, str)
    assert len(summary) > 0


@pytest.mark.asyncio
async def test_summary_empty_context():
    summary = DeepContextEngine().summary({})
    assert summary == "Permission level: confirm"


@pytest.mark.asyncio
async def test_summary_only_system():
    ctx = DeepContextEngine(app_discovery_fn=None, fleet_status_fn=None, get_goals_fn=None)
    result = await ctx.collect()
    s = ctx.summary(result)
    assert "Permission level: confirm" in s
    assert "apps" not in s.lower()
    assert "fleet" not in s.lower()
    assert "goal" not in s.lower()
    assert "capabilit" not in s.lower()
    assert "tool" not in s.lower()


@pytest.mark.asyncio
async def test_summary_partial_fields():
    ctx = DeepContextEngine(
        app_discovery_fn=lambda: [{"name": "A"}],
        get_capabilities_fn=lambda: [{"id": "cap1"}],
        get_permission_level_fn=lambda: "restricted",
    )
    result = await ctx.collect()
    s = ctx.summary(result)
    assert "1 apps" in s
    assert "1 capabilities" in s
    assert "restricted" in s
    assert "fleet" not in s.lower()
    assert "goal" not in s.lower()
    assert "tool" not in s.lower()


@pytest.mark.asyncio
async def test_summary_with_goals_and_fleet():
    ctx = DeepContextEngine(
        fleet_status_fn=lambda: {"devices": [{"id": "d1"}]},
        get_goals_fn=lambda: [{"id": "g1"}],
        get_permission_level_fn=lambda: "admin",
    )
    result = await ctx.collect()
    summary = ctx.summary(result)
    assert "fleet" in summary.lower()
    assert "goal" in summary.lower()
    assert "admin" in summary.lower()
    assert "1 fleet" in summary.lower() or "1 fleet" in summary
