import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import modules.sidecar_supervision as sv


@pytest.fixture
def tmp_run_dir(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sv, "_RUN_DIR", run_dir)
    return run_dir


@pytest.mark.alpha_constitutional_gate
def test_sidecar_lock_roundtrip(tmp_run_dir):
    lock = sv.SidecarLock(
        instance_id="inst-1",
        pid=1234,
        parent_pid=1,
        exe_path="C:\\Sentinel\\sidecar.exe",
        port=8765,
        start_time="2026-08-04T15:00:00",
    )
    lock.write()
    raw = json.loads(lock.lock_path.read_text(encoding="utf-8"))
    assert raw["instance_id"] == "inst-1"
    assert raw["pid"] == 1234
    assert raw["port"] == 8765
    lock.remove()
    assert not lock.lock_path.exists()


@pytest.mark.alpha_constitutional_gate
def test_corrupt_lock_file_removed_not_killed(tmp_run_dir):
    bad = tmp_run_dir / f"{sv._LOCK_PREFIX}bad.lock"
    bad.write_text("not json", encoding="utf-8")
    killed = sv.verified_orphan_cleanup("C:\\Sentinel\\sidecar.exe")
    assert killed == []
    assert not bad.exists()


@pytest.mark.alpha_constitutional_gate
def test_verified_cleanup_removes_lock_for_dead_pid_only(tmp_run_dir):
    dead_pid = 99999999
    lock = sv.SidecarLock(
        instance_id="dead",
        pid=dead_pid,
        parent_pid=1,
        exe_path="C:\\Sentinel\\sidecar.exe",
        port=8765,
        start_time="2026-08-04T15:00:00",
    )
    lock.write()
    killed = sv.verified_orphan_cleanup("C:\\Sentinel\\sidecar.exe")
    assert killed == []
    assert not lock.lock_path.exists()


@pytest.mark.alpha_constitutional_gate
def test_parent_monitor_calls_orphan_callback_and_exits(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(sv, "_process_exists", lambda _pid: False)
        on_orphan = MagicMock()
        monitor = sv.ParentMonitor(parent_pid=1, on_orphan=on_orphan)
        monitor._interval = 0.01
        with patch("modules.sidecar_supervision.os._exit", side_effect=SystemExit(0)):
            with pytest.raises(SystemExit):
                monitor._loop()
        on_orphan.assert_called_once()


@pytest.mark.alpha_constitutional_gate
def test_lifecycle_register_writes_lock_and_starts_monitor(tmp_run_dir, monkeypatch):
    with monkeypatch.context() as m:
        m.setenv("SENTINEL_PARENT_PID", str(os.getppid()))
        lifecycle = sv.SidecarLifecycle(port=8765, instance_id="test-inst")
        m.setattr(lifecycle, "_monitor", MagicMock())
        m.setattr(lifecycle._monitor, "start", MagicMock())
        lifecycle.register()
        assert lifecycle._lock is not None
        assert lifecycle._lock.lock_path.exists()
        lifecycle.unregister()
        assert not lifecycle._lock.lock_path.exists()
