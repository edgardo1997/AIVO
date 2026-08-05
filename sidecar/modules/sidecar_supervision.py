"""Authoritative sidecar process ownership, parent monitoring and safe orphan cleanup.

Sidecars write a Sentinel-owned lock file with identity metadata.
Startup cleanup only terminates a stale sidecar when the lock file, process
path, instance metadata and parent death can all be verified.
"""

from __future__ import annotations

import atexit
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from windows_acl import protect_path, sentinel_storage_paths

logger = logging.getLogger("sentinel.sidecar_supervision")

_RUN_DIR = Path(sentinel_storage_paths()["sentinel_config"]) / "run"
_LOCK_PREFIX = "sentinel-sidecar-"


def _run_dir() -> Path:
    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    return _RUN_DIR


def _my_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    return str(Path(sys.argv[0]).resolve())


def _process_exists(pid: int) -> bool:
    try:
        return psutil.pid_exists(pid)
    except Exception:
        return False


def _process_info(pid: int) -> Optional[psutil.Process]:
    try:
        return psutil.Process(pid)
    except psutil.NoSuchProcess:
        return None


def _sidecar_processes() -> List[Dict[str, Any]]:
    """Return sidecar.exe PIDs with parent PID and executable path using psutil."""
    out = []
    for proc in psutil.process_iter(["pid", "ppid", "exe", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == "sidecar.exe":
                out.append({
                    "pid": proc.info["pid"],
                    "parent_pid": proc.info["ppid"] or 0,
                    "exe_path": (proc.info["exe"] or ""),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


class SidecarLock:
    """Identity record for a single sidecar process."""

    def __init__(
        self,
        instance_id: str,
        pid: int,
        parent_pid: int,
        exe_path: str,
        port: int,
        start_time: str,
        session_token: str = "",
    ):
        self.instance_id = instance_id
        self.pid = pid
        self.parent_pid = parent_pid
        self.exe_path = exe_path
        self.port = port
        self.start_time = start_time
        self.session_token = session_token

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "pid": self.pid,
            "parent_pid": self.parent_pid,
            "exe_path": self.exe_path,
            "port": self.port,
            "start_time": self.start_time,
            "session_token": self.session_token,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SidecarLock":
        return cls(
            instance_id=data["instance_id"],
            pid=int(data["pid"]),
            parent_pid=int(data["parent_pid"]),
            exe_path=data.get("exe_path", ""),
            port=int(data.get("port", 0)),
            start_time=data.get("start_time", ""),
            session_token=data.get("session_token", ""),
        )

    @property
    def lock_path(self) -> Path:
        return _run_dir() / f"{_LOCK_PREFIX}{self.instance_id}.lock"

    def write(self) -> None:
        tmp = self.lock_path.with_suffix(f".tmp.{uuid.uuid4().hex}")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(self.lock_path)
        protect_path(str(self.lock_path), directory=False)

    def remove(self) -> None:
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except Exception:
            pass


def _all_lock_paths() -> List[Path]:
    return sorted(_run_dir().glob(f"{_LOCK_PREFIX}*.lock"))


def _read_lock(path: Path) -> Optional[SidecarLock]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SidecarLock.from_dict(data)
    except Exception:
        return None


def _is_verified_stale(lock: SidecarLock) -> bool:
    """Only true when the lock, executable path, and parent death all match."""
    if lock.pid == os.getpid():
        return False

    proc = _process_info(lock.pid)
    if proc is None:
        return False

    try:
        if proc.name().lower() != "sidecar.exe":
            return False
        real_path = Path(proc.exe()).resolve()
        expected_path = Path(lock.exe_path).resolve()
        if real_path != expected_path and real_path.name != expected_path.name:
            return False
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False

    # Parent death is the key sentinel-owned signal.
    if _process_exists(lock.parent_pid):
        return False

    return True


def _lock_for_pid(pid: int) -> Optional[SidecarLock]:
    for path in _all_lock_paths():
        lock = _read_lock(path)
        if lock and lock.pid == pid:
            return lock
    return None


def verified_orphan_cleanup(exe_path: Optional[str] = None) -> List[int]:
    """Terminate only verified stale Sentinel sidecars, never by name alone."""
    killed: List[int] = []
    expected = Path(exe_path or _my_exe_path()).resolve()

    # First pass: terminate processes with a valid Sentinel lock and dead parent.
    for path in _all_lock_paths():
        lock = _read_lock(path)
        if lock is None:
            try:
                path.unlink()
            except Exception:
                pass
            continue

        if lock.pid == os.getpid():
            continue

        if _process_info(lock.pid) is None:
            lock.remove()
            continue

        if not _is_verified_stale(lock):
            continue

        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(lock.pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                killed.append(lock.pid)
                logger.info("Terminated verified orphan sidecar pid=%s instance=%s", lock.pid, lock.instance_id)
        except Exception:
            pass
        finally:
            lock.remove()

    # Second pass (safety net): lock-less sidecar.exe with dead parent and matching path.
    current_pid = os.getpid()
    current_ppid = os.getppid()
    for proc in _sidecar_processes():
        if proc["pid"] == current_pid or proc["pid"] == current_ppid:
            continue
        if _lock_for_pid(proc["pid"]) is not None:
            continue
        if _process_exists(proc["parent_pid"]):
            continue
        try:
            real = Path(proc["exe_path"]).resolve()
        except Exception:
            continue
        # Only terminate the exact executable we are responsible for;
        # never kill sidecar.exe processes from other installations or tests.
        if real != expected:
            continue
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(proc["pid"]), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                killed.append(proc["pid"])
                logger.info("Terminated lock-less orphan sidecar pid=%s", proc["pid"])
        except Exception:
            pass
    return killed


class ParentMonitor:
    """Background thread: exit gracefully when the parent process disappears."""

    _interval = 2.0

    def __init__(self, parent_pid: int, on_orphan: Optional[callable] = None):
        self._parent_pid = parent_pid
        self._on_orphan = on_orphan
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sidecar-parent-monitor")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            if not _process_exists(self._parent_pid):
                logger.warning("Parent process %s disappeared; sidecar exiting gracefully.", self._parent_pid)
                if self._on_orphan:
                    try:
                        self._on_orphan()
                    except Exception:
                        pass
                os._exit(0)


class SidecarLifecycle:
    """One instance per sidecar process: write lock, monitor parent, cleanup."""

    def __init__(self, port: int, instance_id: Optional[str] = None):
        self._instance_id = instance_id or str(uuid.uuid4())
        self._port = port
        raw_parent = os.environ.get("SENTINEL_PARENT_PID", "")
        self._parent_pid = int(raw_parent) if raw_parent.isdigit() else 0
        self._session_token = os.environ.get("SENTINEL_SESSION_TOKEN", "")
        self._lock: Optional[SidecarLock] = None
        self._monitor: Optional[ParentMonitor] = None

    def register(self) -> None:
        """Write identity lock, clean verified orphans, start parent monitor."""
        verified_orphan_cleanup(_my_exe_path())

        self._lock = SidecarLock(
            instance_id=self._instance_id,
            pid=os.getpid(),
            parent_pid=self._parent_pid,
            exe_path=_my_exe_path(),
            port=self._port,
            start_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            session_token=self._session_token,
        )
        self._lock.write()
        atexit.register(self._lock.remove)

        if self._parent_pid and self._parent_pid > 1:
            self._monitor = ParentMonitor(self._parent_pid)
            self._monitor.start()
        logger.info("Sidecar registered instance=%s pid=%s parent=%s", self._instance_id, os.getpid(), self._parent_pid)

    def unregister(self) -> None:
        if self._monitor:
            self._monitor.stop()
        if self._lock:
            self._lock.remove()
