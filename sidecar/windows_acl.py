"""Windows ACL enforcement for Sentinel-owned sensitive storage."""

from __future__ import annotations

import csv
import io
import os
import subprocess
from pathlib import Path
from typing import Callable


class AclEnforcementError(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess]


def _run(args: list[str], runner: Runner = subprocess.run, **extra) -> subprocess.CompletedProcess:
    return runner(args, capture_output=True, text=True, timeout=15, shell=False, **extra)


def current_user_sid(runner: Runner = subprocess.run) -> str:
    result = _run(["whoami.exe", "/user", "/fo", "csv", "/nh"], runner)
    if result.returncode != 0:
        raise AclEnforcementError(f"Cannot resolve current Windows SID: {result.stderr.strip()}")
    try:
        sid = next(csv.reader(io.StringIO(result.stdout.strip())))[1].strip()
    except (IndexError, StopIteration, csv.Error) as exc:
        raise AclEnforcementError("whoami returned an invalid SID record") from exc
    if not sid.startswith("S-1-"):
        raise AclEnforcementError("Windows account SID is invalid")
    return sid


def protect_path(
    path: str | Path, *, directory: bool | None = None, required: bool = True, runner: Runner = subprocess.run
) -> bool:
    """Replace broad access with full control for the current user and SYSTEM."""
    if os.name != "nt" or os.environ.get("AIVO_TESTING") == "1":
        return False
    target = Path(path).expanduser().resolve()
    if not target.exists():
        if required:
            raise AclEnforcementError(f"Cannot protect missing path: {target}")
        return False
    is_dir = target.is_dir() if directory is None else directory
    sid = current_user_sid(runner)
    script = r"""
$ErrorActionPreference = 'Stop'
$path = $env:SENTINEL_ACL_PATH
$sid = [System.Security.Principal.SecurityIdentifier]::new($env:SENTINEL_ACL_SID)
$system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$rights = [System.Security.AccessControl.FileSystemRights]::FullControl
$allow = [System.Security.AccessControl.AccessControlType]::Allow
if ($env:SENTINEL_ACL_DIRECTORY -eq '1') {
  $acl = [System.Security.AccessControl.DirectorySecurity]::new()
  $inherit = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
  $propagate = [System.Security.AccessControl.PropagationFlags]::None
} else {
  $acl = [System.Security.AccessControl.FileSecurity]::new()
  $inherit = [System.Security.AccessControl.InheritanceFlags]::None
  $propagate = [System.Security.AccessControl.PropagationFlags]::None
}
$acl.SetAccessRuleProtection($true, $false)
$acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new($sid, $rights, $inherit, $propagate, $allow))
$acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new($system, $rights, $inherit, $propagate, $allow))
if ($env:SENTINEL_ACL_DIRECTORY -eq '1') {
  [System.IO.Directory]::SetAccessControl($path, $acl)
} else {
  [System.IO.File]::SetAccessControl($path, $acl)
}
"""
    env = os.environ.copy()
    env.update(
        {"SENTINEL_ACL_PATH": str(target), "SENTINEL_ACL_SID": sid, "SENTINEL_ACL_DIRECTORY": "1" if is_dir else "0"}
    )
    result = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], runner, env=env)
    if result.returncode != 0:
        if required:
            raise AclEnforcementError(
                f"ACL enforcement failed for {target}: {result.stderr.strip() or result.stdout.strip()}"
            )
        return False
    return True


def sentinel_storage_paths() -> dict[str, Path]:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return {
        "runtime": local / "Sentinel",
        "logs": local / "Sentinel" / "logs",
        "updates": local / "Sentinel" / "updates",
        "tauri": local / "com.aivo.desktop",
        "sentinel_config": Path.home() / ".sentinel",
        "legacy_config": Path.home() / ".aivo",
        "policies": Path.home() / ".sentinel" / "policies",
    }


def secure_runtime_directories() -> dict[str, str]:
    paths = sentinel_storage_paths()
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
        protect_path(path, directory=True)
    return {name: str(path) for name, path in paths.items()}
