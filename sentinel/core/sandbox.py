"""Windows JobObject sandbox for process isolation."""

import logging
import uuid
from ctypes import (
    POINTER, Structure, byref, c_bool, c_char_p, c_size_t, c_ubyte,
    c_uint, c_uint64, c_ushort, c_void_p, c_wchar_p, sizeof, windll,
)
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# Constants
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x0008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x0200
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x0100
JOB_OBJECT_LIMIT_CPU_RATE_CONTROL = 0x4000

JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1
JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4

JobObjectExtendedLimitInformation = 9
JobObjectCpuRateControlInformation = 15

PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
PROCESS_SUSPEND_RESUME = 0x0800

_kernel32 = windll.kernel32


# --- Windows API type definitions ---

class _LARGE_INTEGER(Structure):
    _fields_ = [("QuadPart", c_uint64)]


class _IO_COUNTERS(Structure):
    _fields_ = [
        ("ReadOperationCount", c_uint64),
        ("WriteOperationCount", c_uint64),
        ("OtherOperationCount", c_uint64),
        ("ReadTransferCount", c_uint64),
        ("WriteTransferCount", c_uint64),
        ("OtherTransferCount", c_uint64),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", _LARGE_INTEGER),
        ("PerJobUserTimeLimit", _LARGE_INTEGER),
        ("LimitFlags", c_uint),
        ("MinimumWorkingSetSize", c_size_t),
        ("MaximumWorkingSetSize", c_size_t),
        ("ActiveProcessLimit", c_uint),
        ("Affinity", c_uint64 if sizeof(c_void_p) == 8 else c_uint),
        ("ChildProcessRateLimit", c_uint),
        ("Bookmark", c_void_p),
        ("SchedulingClass", c_ushort),
        ("Spare", c_uint),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", c_size_t),
        ("JobMemoryLimit", c_size_t),
        ("PeakProcessMemoryUsed", c_size_t),
        ("PeakJobMemoryUsed", c_size_t),
    ]


class _JOBOBJECT_CPU_RATE_CONTROL_INFORMATION(Structure):
    _fields_ = [
        ("ControlFlags", c_uint),
        ("CpuRate", c_uint),
    ]


# --- Kernel32 function bindings ---

def _create_job_object(name: Optional[str]) -> Optional[int]:
    name_w = wintypes.LPCWSTR(c_wchar_p(name)) if name else None
    handle = _kernel32.CreateJobObjectW(None, name_w)
    if not handle:
        log.warning("CreateJobObjectW failed: %d", _kernel32.GetLastError())
        return None
    return handle


def _close_handle(handle: int) -> bool:
    return bool(_kernel32.CloseHandle(wintypes.HANDLE(handle)))


def _set_extended_info(handle: int, flags: int, process_limit: int = 0, job_memory_mb: int = 0) -> bool:
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = flags
    info.BasicLimitInformation.ActiveProcessLimit = process_limit
    info.JobMemoryLimit = c_size_t(job_memory_mb * 1024 * 1024) if job_memory_mb else c_size_t(0)
    info.ProcessMemoryLimit = c_size_t(job_memory_mb * 1024 * 1024) if job_memory_mb else c_size_t(0)

    result = _kernel32.SetInformationJobObject(
        wintypes.HANDLE(handle),
        JobObjectExtendedLimitInformation,
        byref(info),
        sizeof(info),
    )
    if not result:
        log.warning("SetInformationJobObject failed: %d", _kernel32.GetLastError())
        return False
    return True


def _set_cpu_rate(handle: int, rate_pct: int) -> bool:
    rate_info = _JOBOBJECT_CPU_RATE_CONTROL_INFORMATION()
    rate_info.ControlFlags = JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    rate_info.CpuRate = rate_pct * 100

    result = _kernel32.SetInformationJobObject(
        wintypes.HANDLE(handle),
        JobObjectCpuRateControlInformation,
        byref(rate_info),
        sizeof(rate_info),
    )
    if not result:
        log.warning("SetInformationJobObject CPU rate failed: %d", _kernel32.GetLastError())
        return False
    return True


def _assign_process(handle: int, pid: int) -> bool:
    proc_handle = _kernel32.OpenProcess(
        PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME,
        False,
        pid,
    )
    if not proc_handle:
        log.warning("OpenProcess(%d) failed: %d", pid, _kernel32.GetLastError())
        return False
    try:
        result = _kernel32.AssignProcessToJobObject(wintypes.HANDLE(handle), wintypes.HANDLE(proc_handle))
        if not result:
            log.warning("AssignProcessToJobObject(%d) failed: %d", pid, _kernel32.GetLastError())
            return False
        return True
    finally:
        _kernel32.CloseHandle(proc_handle)


def _terminate_job(handle: int) -> bool:
    result = _kernel32.TerminateJobObject(wintypes.HANDLE(handle), 1)
    if not result:
        log.warning("TerminateJobObject failed: %d", _kernel32.GetLastError())
    return bool(result)


# --- Sandbox Manager ---

@dataclass
class SandboxLimits:
    max_processes: int = 0
    memory_limit_mb: int = 0
    cpu_percent: int = 0
    kill_on_close: bool = True


@dataclass
class SandboxInfo:
    id: str
    name: str
    created_at: str
    process_count: int
    limits: SandboxLimits
    is_active: bool


class Sandbox:
    def __init__(self, sandbox_id: str, name: str, handle: int, limits: SandboxLimits):
        self.id = sandbox_id
        self.name = name
        self.handle = handle
        self.limits = limits
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.process_pids: List[int] = []


class SandboxManager:
    def __init__(self):
        self._sandboxes: Dict[str, Sandbox] = {}

    def create_sandbox(self, name: Optional[str] = None, limits: Optional[SandboxLimits] = None) -> Optional[str]:
        limits = limits or SandboxLimits()
        sb_id = uuid.uuid4().hex[:12]
        sb_name = name or f"sandbox-{sb_id[:8]}"
        job_name = f"SentinelSandbox_{sb_id}"

        handle = _create_job_object(job_name)
        if not handle:
            log.warning("Failed to create JobObject for sandbox %s", sb_id)
            return None

        flags = 0
        if limits.kill_on_close:
            flags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if limits.max_processes > 0:
            flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        if limits.memory_limit_mb > 0:
            flags |= JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_PROCESS_MEMORY

        if flags:
            if not _set_extended_info(handle, flags, limits.max_processes, limits.memory_limit_mb):
                _close_handle(handle)
                return None

        if limits.cpu_percent > 0:
            if not _set_cpu_rate(handle, limits.cpu_percent):
                _close_handle(handle)
                return None

        sb = Sandbox(sb_id, sb_name, handle, limits)
        self._sandboxes[sb_id] = sb
        log.info("Sandbox %s created (name=%s, handle=%d)", sb_id, sb_name, handle)
        return sb_id

    def assign_process(self, sandbox_id: str, pid: int) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            log.warning("Sandbox %s not found", sandbox_id)
            return False

        if not _assign_process(sb.handle, pid):
            return False

        sb.process_pids.append(pid)
        log.info("Process %d assigned to sandbox %s", pid, sandbox_id)
        return True

    def terminate_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            log.warning("Sandbox %s not found", sandbox_id)
            return False

        if not _terminate_job(sb.handle):
            return False

        sb.process_pids.clear()
        log.info("Sandbox %s terminated", sandbox_id)
        return True

    def close_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.pop(sandbox_id, None)
        if not sb:
            log.warning("Sandbox %s not found", sandbox_id)
            return False

        result = _close_handle(sb.handle)
        if result:
            log.info("Sandbox %s closed", sandbox_id)
        return result

    def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            return None
        return SandboxInfo(
            id=sb.id,
            name=sb.name,
            created_at=sb.created_at,
            process_count=len(sb.process_pids),
            limits=sb.limits,
            is_active=True,
        )

    def list_sandboxes(self) -> List[SandboxInfo]:
        return [
            SandboxInfo(
                id=sb.id,
                name=sb.name,
                created_at=sb.created_at,
                process_count=len(sb.process_pids),
                limits=sb.limits,
                is_active=True,
            )
            for sb in self._sandboxes.values()
        ]

    def cleanup_all(self) -> int:
        count = 0
        for sb_id in list(self._sandboxes.keys()):
            self.terminate_sandbox(sb_id)
            self.close_sandbox(sb_id)
            count += 1
        return count


_manager: Optional[SandboxManager] = None


def _get_manager() -> SandboxManager:
    global _manager
    if _manager is None:
        _manager = SandboxManager()
    return _manager


def create_sandbox(name: Optional[str] = None, limits: Optional[SandboxLimits] = None) -> Optional[str]:
    return _get_manager().create_sandbox(name, limits)


def assign_process(sandbox_id: str, pid: int) -> bool:
    return _get_manager().assign_process(sandbox_id, pid)


def terminate_sandbox(sandbox_id: str) -> bool:
    return _get_manager().terminate_sandbox(sandbox_id)


def close_sandbox(sandbox_id: str) -> bool:
    return _get_manager().close_sandbox(sandbox_id)


def get_sandbox_info(sandbox_id: str) -> Optional[SandboxInfo]:
    return _get_manager().get_sandbox_info(sandbox_id)


def list_sandboxes() -> List[SandboxInfo]:
    return _get_manager().list_sandboxes()


def cleanup_all() -> int:
    return _get_manager().cleanup_all()
