"""Windows process management: list, kill, suspend/resume, priority."""

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger(__name__)

_SYSTEM_PIDS: set[int] = set()
_psutil = None

SYSTEM_PROCESS_NAMES = frozenset({
    "System", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "svchost.exe", "winlogon.exe", "explorer.exe",
    "conhost.exe", "fontdrvhost.exe", "dwm.exe", "SecurityHealthService.exe",
    "MsMpEng.exe", "NisSrv.exe", "spoolsv.exe",
})

PROCESS_PRIORITIES = {
    "idle": 64,
    "below_normal": 16384,
    "normal": 32,
    "above_normal": 32768,
    "high": 128,
    "realtime": 256,
}

PSPRIO_MAP = {
    "idle": "idle",
    "below_normal": "below normal",
    "normal": "normal",
    "above_normal": "above normal",
    "high": "high",
    "realtime": "realtime",
}


@dataclass
class ProcessInfo:
    pid: int
    name: str
    exe: str = ""
    cmdline: str = ""
    status: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    username: str = ""
    is_system: bool = False
    priority: str = ""


@dataclass
class ProcessResult:
    success: bool
    processes: List[ProcessInfo] = field(default_factory=list)
    message: str = ""
    error: str = ""


def _get_psutil():
    global _psutil
    if _psutil is None:
        import psutil as _psutil_mod
        _psutil = _psutil_mod
    return _psutil


def _is_system_process_name(name: str) -> bool:
    return name.lower() in {n.lower() for n in SYSTEM_PROCESS_NAMES}


def _build_process_list(procs) -> List[ProcessInfo]:
    psutil_mod = _get_psutil()
    results = []
    for proc in procs:
        try:
            pinfo = proc.info
            pid = pinfo["pid"]
            name = pinfo.get("name") or ""
            exe = pinfo.get("exe") or ""
            is_sys = _is_system_process_name(name) or pid in _SYSTEM_PIDS
            try:
                p = psutil_mod.Process(pid)
                cmd = " ".join(p.cmdline()) if p.cmdline() else ""
                status = p.status() if hasattr(p, "status") else ""
                cpu = p.cpu_percent(interval=0) if hasattr(p, "cpu_percent") else 0.0
                mem = p.memory_info().rss / (1024 * 1024) if hasattr(p, "memory_info") else 0.0
                user = p.username() if hasattr(p, "username") else ""
                prio = p.nice() if hasattr(p, "nice") else ""
            except (psutil_mod.NoSuchProcess, psutil_mod.AccessDenied, psutil_mod.ZombieProcess):
                cmd, status, cpu, mem, user, prio = "", "", 0.0, 0.0, "", ""
            results.append(ProcessInfo(
                pid=pid, name=name, exe=exe, cmdline=cmd,
                status=status, cpu_percent=cpu, memory_mb=mem,
                username=user, is_system=is_sys, priority=str(prio),
            ))
        except (psutil_mod.NoSuchProcess, psutil_mod.AccessDenied):
            continue
    return results


def list_processes(name_filter: Optional[str] = None, include_system: bool = False) -> ProcessResult:
    psutil_mod = _get_psutil()
    try:
        attrs = ["pid", "name", "exe"]
        procs = psutil_mod.process_iter(attrs=attrs)
        results = _build_process_list(procs)
        if name_filter:
            filt = name_filter.lower()
            results = [p for p in results if filt in p.name.lower() or filt in p.cmdline.lower()]
        if not include_system:
            results = [p for p in results if not p.is_system]
        return ProcessResult(success=True, processes=sorted(results, key=lambda x: x.pid))
    except Exception as e:
        log.warning("list_processes error: %s", e)
        return ProcessResult(success=False, error=str(e))


def kill_process(target: str, force: bool = True) -> ProcessResult:
    psutil_mod = _get_psutil()
    try:
        target_lower = target.lower().strip()
        target_pid = None
        try:
            target_pid = int(target_lower)
        except ValueError:
            pass

        if target_pid is not None:
            pids_to_kill = [target_pid]
        else:
            pids_to_kill = []
            for proc in psutil_mod.process_iter(attrs=["pid", "name"]):
                try:
                    info = proc.info
                    if info["name"] and target_lower in info["name"].lower():
                        pids_to_kill.append(info["pid"])
                except (psutil_mod.NoSuchProcess, psutil_mod.AccessDenied):
                    continue

        if not pids_to_kill:
            return ProcessResult(success=False, error=f"No process matching '{target}' found")

        killed = []
        errors = []
        for pid in pids_to_kill:
            try:
                proc = psutil_mod.Process(pid)
                name = proc.name()
                if _is_system_process_name(name) or pid in _SYSTEM_PIDS:
                    errors.append(f"PID {pid} ({name}): protected system process")
                    continue
                if force:
                    proc.terminate()
                    proc.wait(timeout=3)
                else:
                    proc.terminate()
                killed.append({"pid": pid, "name": name})
            except psutil_mod.NoSuchProcess:
                errors.append(f"PID {pid}: not found")
            except psutil_mod.AccessDenied:
                errors.append(f"PID {pid}: access denied")
            except psutil_mod.TimeoutExpired:
                if force:
                    try:
                        proc.kill()
                        killed.append({"pid": pid, "name": name, "forced": True})
                    except Exception as e:
                        errors.append(f"PID {pid}: {e}")
                else:
                    errors.append(f"PID {pid}: timeout")

        msg = f"Killed {len(killed)} process(es)"
        if errors:
            msg += f", {len(errors)} error(s)"
        return ProcessResult(success=len(killed) > 0, message=msg, error="; ".join(errors) if errors else "")
    except Exception as e:
        log.warning("kill_process error: %s", e)
        return ProcessResult(success=False, error=str(e))


def _open_process_handle(pid: int, access: int):
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    return kernel32.OpenProcess(access, False, pid)


def _close_handle(handle):
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32.CloseHandle(handle)


def _nt_process_action(pid: int, suspend: bool) -> bool:
    import ctypes
    from ctypes import wintypes
    PROCESS_SUSPEND_RESUME = 0x0800

    handle = _open_process_handle(pid, PROCESS_SUSPEND_RESUME)
    if not handle:
        return False
    try:
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        func_name = "NtSuspendProcess" if suspend else "NtResumeProcess"
        func = getattr(ntdll, func_name)
        func.argtypes = [wintypes.HANDLE]
        func.restype = wintypes.DWORD
        result = func(handle)
        return result == 0
    finally:
        _close_handle(handle)


def _validate_target(target: str) -> tuple[Optional[List[int]], Optional[str]]:
    psutil_mod = _get_psutil()
    try:
        target_pid = int(target.strip())
    except ValueError:
        target_pid = None

    if target_pid is not None:
        try:
            proc = psutil_mod.Process(target_pid)
            if _is_system_process_name(proc.name()) or target_pid in _SYSTEM_PIDS:
                return None, f"PID {target_pid} ({proc.name()}): protected system process"
            return [target_pid], None
        except psutil_mod.NoSuchProcess:
            return None, f"PID {target_pid}: not found"
    else:
        target_lower = target.lower().strip()
        pids = []
        for proc in psutil_mod.process_iter(attrs=["pid", "name"]):
            try:
                info = proc.info
                if info["name"] and target_lower in info["name"].lower():
                    if _is_system_process_name(info["name"]) or info["pid"] in _SYSTEM_PIDS:
                        continue
                    pids.append(info["pid"])
            except (psutil_mod.NoSuchProcess, psutil_mod.AccessDenied):
                continue
        if not pids:
            return None, f"No process matching '{target}' found"
        return pids, None


def suspend_process(target: str) -> ProcessResult:
    pids, err = _validate_target(target)
    if err:
        return ProcessResult(success=False, error=err)

    suspended = []
    errors = []
    for pid in pids:
        if _nt_process_action(pid, suspend=True):
            suspended.append(pid)
        else:
            errors.append(f"PID {pid}: suspend failed")

    msg = f"Suspended {len(suspended)} process(es)"
    if errors:
        msg += f", {len(errors)} error(s)"
    return ProcessResult(success=len(suspended) > 0, message=msg, error="; ".join(errors) if errors else "")


def resume_process(target: str) -> ProcessResult:
    pids, err = _validate_target(target)
    if err:
        return ProcessResult(success=False, error=err)

    resumed = []
    errors = []
    for pid in pids:
        if _nt_process_action(pid, suspend=False):
            resumed.append(pid)
        else:
            errors.append(f"PID {pid}: resume failed")

    msg = f"Resumed {len(resumed)} process(es)"
    if errors:
        msg += f", {len(errors)} error(s)"
    return ProcessResult(success=len(resumed) > 0, message=msg, error="; ".join(errors) if errors else "")


def set_priority(target: str, priority: str) -> ProcessResult:
    pids, err = _validate_target(target)
    if err:
        return ProcessResult(success=False, error=err)

    prio_str = PSPRIO_MAP.get(priority.lower())
    if not prio_str:
        valid = ", ".join(PSPRIO_MAP.keys())
        return ProcessResult(success=False, error=f"Invalid priority '{priority}'. Valid: {valid}")

    wmic_name = prio_str.replace(" ", " ")
    changed = []
    errors = []
    for pid in pids:
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 f"(Get-Process -Id {pid}).PriorityClass = '{wmic_name}'"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                changed.append(pid)
            else:
                errors.append(f"PID {pid}: {r.stderr.strip() or r.stdout.strip() or 'failed'}")
        except Exception as e:
            errors.append(f"PID {pid}: {e}")

    msg = f"Changed priority for {len(changed)} process(es)"
    if errors:
        msg += f", {len(errors)} error(s)"
    return ProcessResult(success=len(changed) > 0, message=msg, error="; ".join(errors) if errors else "")


def get_process_info(pid: int) -> Optional[ProcessInfo]:
    psutil_mod = _get_psutil()
    try:
        procs = psutil_mod.process_iter(attrs=["pid", "name", "exe"])
        results = _build_process_list([p for p in procs if p.info["pid"] == pid])
        return results[0] if results else None
    except Exception:
        return None
