import time
from types import SimpleNamespace

import pytest

from modules import proactive
from modules.proactive import (
    format_bytes,
    get_top_process,
    check_thresholds,
    store_metrics_snapshot,
    get_trend,
    dismiss_suggestion,
    execute_suggestion,
    THRESHOLDS,
)


@pytest.fixture(autouse=True)
def reset_state():
    proactive.SUGGESTIONS.clear()
    proactive.METRICS_HISTORY.clear()
    yield
    proactive.SUGGESTIONS.clear()
    proactive.METRICS_HISTORY.clear()


class FakeProc:
    def __init__(self, info):
        self.info = info


def make_psutil(monkeypatch, *, cpu=10.0, mem_percent=10.0, swap_percent=0.0,
                procs=None, disks=None, boot_offset_hours=1.0):
    """Patch psutil functions used by proactive with deterministic values."""
    mem = SimpleNamespace(percent=mem_percent, used=8 * 10**9, total=16 * 10**9)
    swap = SimpleNamespace(percent=swap_percent)
    proc_list = procs if procs is not None else [
        FakeProc({"pid": 1, "name": "a", "cpu_percent": 5.0, "memory_percent": 3.0}),
    ]

    monkeypatch.setattr(proactive.psutil, "cpu_percent", lambda interval=0: cpu)
    monkeypatch.setattr(proactive.psutil, "virtual_memory", lambda: mem)
    monkeypatch.setattr(proactive.psutil, "swap_memory", lambda: swap)
    monkeypatch.setattr(proactive.psutil, "boot_time",
                        lambda: time.time() - boot_offset_hours * 3600)
    monkeypatch.setattr(proactive.psutil, "process_iter",
                        lambda attrs=None: list(proc_list))

    disk_parts = disks if disks is not None else []
    monkeypatch.setattr(
        proactive.psutil, "disk_partitions",
        lambda: [SimpleNamespace(mountpoint=m,
                                 percent=(pct if disks else 0)) for (m, pct, free) in disk_parts]
        if disks else [],
    )
    usage_map = {m: SimpleNamespace(percent=pct, free=free) for (m, pct, free) in disk_parts}
    monkeypatch.setattr(proactive.psutil, "disk_usage",
                        lambda mount: usage_map[mount])


# --- format_bytes ---

@pytest.mark.parametrize("value,expected", [
    (5 * 10**12, "5.0 TB"),
    (3 * 10**9, "3.0 GB"),
    (2 * 10**6, "2.0 MB"),
    (5 * 10**3, "5 KB"),
])
def test_format_bytes(value, expected):
    assert format_bytes(value) == expected


# --- get_top_process ---

def test_get_top_process_returns_highest(monkeypatch):
    procs = [
        FakeProc({"pid": 1, "name": "low", "cpu_percent": 5.0, "memory_percent": 1.0}),
        FakeProc({"pid": 2, "name": "high", "cpu_percent": 90.0, "memory_percent": 2.0}),
    ]
    monkeypatch.setattr(proactive.psutil, "process_iter", lambda attrs=None: procs)
    val, name, pid = get_top_process("cpu")
    assert name == "high"
    assert pid == 2
    assert val == 90.0


def test_get_top_process_empty(monkeypatch):
    monkeypatch.setattr(proactive.psutil, "process_iter", lambda attrs=None: [])
    assert get_top_process("cpu") == (0, "unknown", 0)


# --- check_thresholds ---

def test_check_thresholds_no_alerts_when_healthy(monkeypatch):
    make_psutil(monkeypatch, cpu=10, mem_percent=10)
    check_thresholds()
    assert proactive.SUGGESTIONS == []


def test_check_thresholds_critical_cpu(monkeypatch):
    make_psutil(monkeypatch, cpu=95, mem_percent=10)
    check_thresholds()
    cpu_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("cpu_")]
    assert cpu_alerts
    assert cpu_alerts[0]["priority"] == "warning"
    assert "95" in cpu_alerts[0]["message"]


def test_check_thresholds_warning_cpu(monkeypatch):
    make_psutil(monkeypatch, cpu=75, mem_percent=10)
    check_thresholds()
    cpu_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("cpu_")]
    assert cpu_alerts
    assert cpu_alerts[0]["priority"] == "info"


def test_check_thresholds_critical_memory(monkeypatch):
    make_psutil(monkeypatch, cpu=10, mem_percent=95)
    check_thresholds()
    mem_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("mem_")]
    assert mem_alerts
    assert mem_alerts[0]["priority"] == "critical"


def test_check_thresholds_warning_memory(monkeypatch):
    make_psutil(monkeypatch, cpu=10, mem_percent=80)
    check_thresholds()
    mem_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("mem_")]
    assert mem_alerts
    assert mem_alerts[0]["priority"] == "warning"


def test_check_thresholds_high_swap(monkeypatch):
    make_psutil(monkeypatch, swap_percent=90)
    check_thresholds()
    swap_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("swap_")]
    assert swap_alerts
    assert swap_alerts[0]["priority"] == "critical"


def test_check_thresholds_long_uptime(monkeypatch):
    make_psutil(monkeypatch, boot_offset_hours=100)
    check_thresholds()
    uptime_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("uptime_")]
    assert uptime_alerts


def test_check_thresholds_many_processes(monkeypatch):
    procs = [FakeProc({"pid": i, "name": "p", "cpu_percent": 0.0, "memory_percent": 0.0})
             for i in range(THRESHOLDS["process_count_high"] + 5)]
    make_psutil(monkeypatch, procs=procs)
    check_thresholds()
    proc_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("procs_")]
    assert proc_alerts


def test_check_thresholds_critical_disk(monkeypatch):
    make_psutil(monkeypatch, disks=[("C:", 97, 10**9)])
    check_thresholds()
    disk_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("disk_")]
    assert disk_alerts
    assert disk_alerts[0]["priority"] == "critical"


def test_check_thresholds_warning_disk(monkeypatch):
    make_psutil(monkeypatch, disks=[("D:", 88, 10**9)])
    check_thresholds()
    disk_alerts = [s for s in proactive.SUGGESTIONS if s["id"].startswith("disk_")]
    assert disk_alerts
    assert disk_alerts[0]["priority"] == "warning"


def test_check_thresholds_disk_permission_error(monkeypatch):
    make_psutil(monkeypatch, disks=[("E:", 99, 10**9)])

    def raise_perm(mount):
        raise PermissionError("denied")

    monkeypatch.setattr(proactive.psutil, "disk_usage", raise_perm)
    check_thresholds()
    assert [s for s in proactive.SUGGESTIONS if s["id"].startswith("disk_")] == []


# --- store_metrics_snapshot ---

def test_store_metrics_snapshot_appends(monkeypatch):
    make_psutil(monkeypatch, cpu=42, mem_percent=50)
    store_metrics_snapshot()
    assert len(proactive.METRICS_HISTORY) == 1
    snap = proactive.METRICS_HISTORY[0]
    assert snap["cpu_percent"] == 42
    assert snap["memory_percent"] == 50


def test_store_metrics_snapshot_trims_to_max(monkeypatch):
    make_psutil(monkeypatch, cpu=10, mem_percent=10)
    for _ in range(proactive.MAX_HISTORY + 10):
        store_metrics_snapshot()
    assert len(proactive.METRICS_HISTORY) == proactive.MAX_HISTORY


# --- get_trend ---

def test_get_trend_insufficient_history():
    assert get_trend() == {}


def test_get_trend_detects_upward():
    for i in range(10):
        proactive.METRICS_HISTORY.append(
            {"cpu_percent": 10, "memory_percent": 10, "disk_percent": 10, "process_count": 100})
    for i in range(10):
        proactive.METRICS_HISTORY.append(
            {"cpu_percent": 80, "memory_percent": 80, "disk_percent": 80, "process_count": 200})
    trends = get_trend()
    assert trends["cpu_percent"]["direction"] == "up"
    assert trends["memory_percent"]["direction"] == "up"


def test_get_trend_detects_downward():
    for i in range(10):
        proactive.METRICS_HISTORY.append(
            {"cpu_percent": 80, "memory_percent": 80, "disk_percent": 80, "process_count": 200})
    for i in range(10):
        proactive.METRICS_HISTORY.append(
            {"cpu_percent": 10, "memory_percent": 10, "disk_percent": 10, "process_count": 100})
    trends = get_trend()
    assert trends["cpu_percent"]["direction"] == "down"


def test_get_trend_detects_stable():
    for i in range(20):
        proactive.METRICS_HISTORY.append(
            {"cpu_percent": 50, "memory_percent": 50, "disk_percent": 50, "process_count": 100})
    trends = get_trend()
    assert trends["cpu_percent"]["direction"] == "stable"


# --- dismiss_suggestion ---

def test_dismiss_suggestion_marks_dismissed():
    proactive.SUGGESTIONS.append({"id": "x1", "actions": []})
    assert dismiss_suggestion("x1") == {"status": "dismissed"}
    assert proactive.SUGGESTIONS[0]["dismissed"] is True


def test_dismiss_suggestion_not_found():
    assert dismiss_suggestion("nope") == {"status": "not_found"}


# --- execute_suggestion ---

def test_execute_suggestion_not_found():
    assert execute_suggestion("nope") == {"status": "not_found"}


def test_execute_suggestion_no_actions():
    proactive.SUGGESTIONS.append({"id": "s1", "actions": []})
    assert execute_suggestion("s1") == {"status": "no_actions"}


def test_execute_suggestion_launch(monkeypatch):
    proactive.SUGGESTIONS.append(
        {"id": "s1", "actions": [{"label": "l", "action": "launch:taskmgr"}]})
    calls = {}
    monkeypatch.setattr(proactive, "log_action", lambda *a, **k: None)
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.setdefault("popen", True))
    result = execute_suggestion("s1")
    assert result["status"] == "executed"
    assert calls.get("popen")


def test_execute_suggestion_kill_top_cpu(monkeypatch):
    proactive.SUGGESTIONS.append(
        {"id": "s1", "actions": [{"label": "l", "action": "kill_top_cpu"}]})
    procs = [FakeProc({"pid": 7, "cpu_percent": 99.0})]
    monkeypatch.setattr(proactive.psutil, "process_iter", lambda attrs=None: procs)
    terminated = {}

    class FakeProcess:
        def __init__(self, pid):
            terminated["pid"] = pid

        def terminate(self):
            terminated["called"] = True

    monkeypatch.setattr(proactive.psutil, "Process", FakeProcess)
    monkeypatch.setattr(proactive, "log_action", lambda *a, **k: None)
    result = execute_suggestion("s1")
    assert result["status"] == "executed"
    assert terminated["pid"] == 7
    assert terminated["called"]


def test_execute_suggestion_kill_top_ram(monkeypatch):
    proactive.SUGGESTIONS.append(
        {"id": "s1", "actions": [{"label": "l", "action": "kill_top_ram"}]})
    procs = [FakeProc({"pid": 9, "memory_percent": 88.0})]
    monkeypatch.setattr(proactive.psutil, "process_iter", lambda attrs=None: procs)
    terminated = {}

    class FakeProcess:
        def __init__(self, pid):
            terminated["pid"] = pid

        def terminate(self):
            terminated["called"] = True

    monkeypatch.setattr(proactive.psutil, "Process", FakeProcess)
    result = execute_suggestion("s1")
    assert result["status"] == "executed"
    assert terminated["pid"] == 9


def test_execute_suggestion_unhandled_action():
    proactive.SUGGESTIONS.append(
        {"id": "s1", "actions": [{"label": "l", "action": "suggest:something"}]})
    result = execute_suggestion("s1")
    assert result["status"] == "unhandled_action"


def test_execute_suggestion_skips_dismissed():
    proactive.SUGGESTIONS.append(
        {"id": "s1", "dismissed": True, "actions": [{"action": "kill_top_cpu"}]})
    assert execute_suggestion("s1") == {"status": "not_found"}
