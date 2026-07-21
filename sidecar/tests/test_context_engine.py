import time
from unittest.mock import AsyncMock

import pytest

from sentinel.core.context import ContextEngine, SystemContext


@pytest.mark.security
def test_network_context_does_not_enumerate_connections_by_default(monkeypatch):
    engine = ContextEngine(collect_processes=False)

    def forbidden():
        raise AssertionError("active connections must be opt-in")

    monkeypatch.setattr("sentinel.core.context.psutil.net_connections", forbidden)
    network = engine._collect_network()

    assert network["connections"] == []
    assert network["connection_count"] is None


@pytest.mark.unit
def test_network_connection_collection_is_explicit(monkeypatch):
    engine = ContextEngine(collect_processes=False, collect_connections=True)
    monkeypatch.setattr("sentinel.core.context.psutil.net_connections", lambda: [])

    network = engine._collect_network()

    assert network["connections"] == []
    assert network["connection_count"] == 0


@pytest.mark.asyncio
@pytest.mark.security
async def test_process_rich_cache_never_leaks_to_privacy_safe_request():
    engine = ContextEngine(collect_processes=True)
    engine._last_context = SystemContext(processes=[{"pid": 42, "name": "private.exe"}])
    engine._last_included_processes = True
    engine._cache_deadline = time.monotonic() + 60

    safe = await engine.collect(include_processes=False)

    assert safe.processes == []
    assert engine.get_last_context().processes == [{"pid": 42, "name": "private.exe"}]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_process_request_does_not_reuse_process_free_cache():
    engine = ContextEngine(collect_processes=False)
    engine._last_context = SystemContext(processes=[])
    engine._last_included_processes = False
    engine._cache_deadline = time.monotonic() + 60
    engine._collect_cpu_async = AsyncMock(return_value={"percent": 1})
    engine._collect_memory_async = AsyncMock(return_value={})
    engine._collect_disk_async = AsyncMock(return_value={})
    engine._collect_network_async = AsyncMock(return_value={})
    engine._collect_boot_time_async = AsyncMock(return_value=1.0)
    engine._get_processes_async = AsyncMock(return_value=[{"pid": 7}])

    rich = await engine.collect(include_processes=True)

    assert rich.processes == [{"pid": 7}]
    engine._get_processes_async.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_matching_cache_mode_reuses_same_context():
    engine = ContextEngine(collect_processes=False)
    cached = SystemContext(cpu={"percent": 5})
    engine._last_context = cached
    engine._last_included_processes = False
    engine._cache_deadline = time.monotonic() + 60

    assert await engine.collect(include_processes=False) is cached
