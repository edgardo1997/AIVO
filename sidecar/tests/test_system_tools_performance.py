from unittest.mock import AsyncMock

import pytest

from sentinel.tools.system_tools import CpuInfoTool, NetworkInfoTool, ProcessListTool, SystemInfoTool


def _cached_context() -> dict:
    return {
        "system": {
            "cpu": {
                "percent": 12.5,
                "per_core": [10.0, 15.0],
                "cores_logical": 2,
                "frequency": {"current": 3000.0, "min": 1000.0, "max": 4000.0},
                "load_avg": [0.1, 0.2, 0.3],
            },
            "memory": {
                "virtual": {"total": 100, "available": 60, "used": 40, "percent": 40.0}
            },
            "disk": {"partitions": [{"total": 200, "free": 120, "percent": 40.0}]},
            "network": {"bytes_sent": 10, "bytes_recv": 20},
            "boot_time": 1.0,
        }
    }


@pytest.mark.asyncio
@pytest.mark.unit
async def test_system_info_reuses_collected_context(monkeypatch):
    monkeypatch.setattr(
        "sentinel.tools.system_tools.psutil.cpu_percent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate CPU probe")),
    )

    result = await SystemInfoTool().execute({}, _cached_context())

    assert result.success is True
    assert result.data["cpu"] == {"percent": 12.5, "cores": 2}
    assert result.data["memory"]["available"] == 60


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cpu_info_reuses_collected_context(monkeypatch):
    monkeypatch.setattr(
        "sentinel.tools.system_tools.psutil.cpu_percent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate CPU probe")),
    )

    result = await CpuInfoTool().execute({}, _cached_context())

    assert result.success is True
    assert result.data["overall"] == 12.5
    assert result.data["per_core"] == [10.0, 15.0]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_network_connection_scan_runs_off_event_loop(monkeypatch):
    to_thread = AsyncMock(return_value=[])
    monkeypatch.setattr("sentinel.tools.system_tools.asyncio.to_thread", to_thread)

    result = await NetworkInfoTool().execute({}, {})

    assert result.success is True
    to_thread.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_process_scan_runs_off_event_loop(monkeypatch):
    to_thread = AsyncMock(return_value=[{"pid": 1, "name": "one", "cpu_percent": 1.0}])
    monkeypatch.setattr("sentinel.tools.system_tools.asyncio.to_thread", to_thread)

    result = await ProcessListTool().execute({"limit": 1}, {})

    assert result.success is True
    assert result.data["total"] == 1
    to_thread.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_process_scan_can_skip_expensive_memory_queries(monkeypatch):
    to_thread = AsyncMock(return_value=[])
    monkeypatch.setattr("sentinel.tools.system_tools.asyncio.to_thread", to_thread)

    await ProcessListTool().execute({"limit": 5, "include_memory": False}, {})

    assert to_thread.await_args.kwargs["include_memory"] is False
