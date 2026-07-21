"""Sentinel Windows installer: service registration, firewall, scheduled task."""

import argparse
import logging
import os
import shlex
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

log = logging.getLogger("sentinel.installer")

SENTINEL_SERVICE_NAME = "SentinelAI"
SENTINEL_DISPLAY_NAME = "Sentinel AI Service"
SENTINEL_DESCRIPTION = "Sentinel AI — Trust layer for AI-driven OS control"

FIREWALL_RULE_NAME = "Sentinel AI Service"
SENTINEL_PORT = 8079

REG_UNINSTALL_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SentinelAI"


def _sentinel_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _python_path() -> str:
    return sys.executable


def _sidecar_script() -> str:
    return str(_sentinel_root() / "sidecar" / "main.py")


def _run(cmd: list[str], capture: bool = True, input: str | None = None) -> subprocess.CompletedProcess:
    log.debug("Running: %s", shlex.join(cmd))
    try:
        return subprocess.run(cmd, capture_output=capture, text=True, timeout=30, input=input)
    except FileNotFoundError:
        raise RuntimeError(f"Command not found: {cmd[0]}")


# --- Service ---

def _sc_cmd(action: str, *args: str) -> list[str]:
    return ["sc.exe", action, SENTINEL_SERVICE_NAME, *args]


def install_service() -> dict:
    python_exe = _python_path()
    script = _sidecar_script()
    bin_path = f"{python_exe} {script} --service"

    log.info("Creating service: %s", SENTINEL_SERVICE_NAME)
    r = _run(_sc_cmd("create", f"binPath={bin_path}", "start=auto", f"DisplayName={SENTINEL_DISPLAY_NAME}"))
    if r.returncode != 0:
        return {"success": False, "error": f"sc create failed: {r.stderr.strip() or r.stdout.strip()}"}

    _run(_sc_cmd("description", SENTINEL_DESCRIPTION))
    log.info("Service created: %s", SENTINEL_SERVICE_NAME)
    return {"success": True, "message": f"Service '{SENTINEL_SERVICE_NAME}' created"}


def uninstall_service() -> dict:
    r = _run(_sc_cmd("stop"))
    if r.returncode != 0:
        log.warning("Service stop: %s", r.stderr.strip())

    r = _run(_sc_cmd("delete"))
    if r.returncode != 0:
        return {"success": False, "error": f"sc delete failed: {r.stderr.strip()}"}

    log.info("Service deleted: %s", SENTINEL_SERVICE_NAME)
    return {"success": True, "message": f"Service '{SENTINEL_SERVICE_NAME}' deleted"}


def start_service() -> dict:
    r = _run(_sc_cmd("start"))
    if r.returncode != 0:
        return {"success": False, "error": f"sc start failed: {r.stderr.strip()}"}
    return {"success": True, "message": "Service started"}


def stop_service_cmd() -> dict:
    r = _run(_sc_cmd("stop"))
    if r.returncode != 0:
        return {"success": False, "error": f"sc stop failed: {r.stderr.strip()}"}
    return {"success": True, "message": "Service stopped"}


def service_status() -> dict:
    r = _run(_sc_cmd("query"))
    if r.returncode != 0:
        return {"success": False, "error": "Service not found", "status": "not_found"}
    for line in r.stdout.splitlines():
        if "STATE" in line:
            state = line.split(":")[-1].strip()
            running = "RUNNING" in state.upper()
            return {"success": True, "status": "running" if running else "stopped", "raw": state.strip()}
    return {"success": False, "error": "Could not parse service state"}


# --- Firewall ---

def install_firewall() -> dict:
    r = _run(["netsh", "advfirewall", "firewall", "add", "rule",
              f"name={FIREWALL_RULE_NAME}",
              "dir=in", "action=allow", "protocol=TCP", f"localport={SENTINEL_PORT}",
              "profile=private,domain"])
    if r.returncode != 0:
        return {"success": False, "error": f"netsh failed: {r.stderr.strip()}"}
    log.info("Firewall rule added: %s (port %d)", FIREWALL_RULE_NAME, SENTINEL_PORT)
    return {"success": True, "message": f"Firewall rule '{FIREWALL_RULE_NAME}' added"}


def uninstall_firewall() -> dict:
    r = _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={FIREWALL_RULE_NAME}"])
    if r.returncode != 0:
        return {"success": False, "error": f"netsh delete failed: {r.stderr.strip()}"}
    return {"success": True, "message": f"Firewall rule '{FIREWALL_RULE_NAME}' deleted"}


# --- Scheduled Task (autostart on user login) ---

def install_scheduled_task() -> dict:
    python_exe = _python_path()
    script = _sidecar_script()
    task_name = f"{SENTINEL_SERVICE_NAME}User"
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{SENTINEL_DESCRIPTION}</Description></RegistrationInfo>
  <Triggers><LogonTrigger><UserId>currentuser</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="author"><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><ExecutionTimeLimit>PT0S</ExecutionTimeLimit></Settings>
  <Actions><Exec><Command>{python_exe}</Command><Arguments>"{script}" --tray</Arguments></Exec></Actions>
</Task>"""
    r = _run(["schtasks", "/create", "/tn", task_name, "/xml", "-", "/f"], input=xml)
    if r.returncode != 0:
        return {"success": False, "error": f"schtasks failed: {r.stderr.strip()}"}
    log.info("Scheduled task created: %s", task_name)
    return {"success": True, "message": f"Scheduled task '{task_name}' created"}


def uninstall_scheduled_task() -> dict:
    task_name = f"{SENTINEL_SERVICE_NAME}User"
    r = _run(["schtasks", "/delete", "/tn", task_name, "/f"])
    if r.returncode != 0:
        return {"success": False, "error": f"schtasks delete failed: {r.stderr.strip()}"}
    return {"success": True, "message": f"Scheduled task '{task_name}' deleted"}


# --- Registry (uninstall info) ---

def write_uninstall_registry(install_dir: str) -> dict:
    try:
        with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, REG_UNINSTALL_PATH) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Sentinel AI")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.0.0")
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Sentinel AI")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            uninstall_str = f'"{sys.executable}" -m pip uninstall sentinel -y'
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_str)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        log.info("Uninstall registry written: %s", REG_UNINSTALL_PATH)
        return {"success": True, "message": "Uninstall registry entry created"}
    except PermissionError:
        return {"success": False, "error": "Permission denied (run as administrator)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def remove_uninstall_registry() -> dict:
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, REG_UNINSTALL_PATH)
        return {"success": True, "message": "Uninstall registry entry removed"}
    except FileNotFoundError:
        return {"success": True, "message": "No uninstall registry entry found"}
    except PermissionError:
        return {"success": False, "error": "Permission denied (run as administrator)"}


# --- Full install / uninstall ---

def full_install() -> dict:
    results = {}
    install_dir = str(_sentinel_root())

    results["service"] = install_service()
    results["firewall"] = install_firewall()
    results["registry"] = write_uninstall_registry(install_dir)
    results["start"] = start_service()

    success = all(r.get("success") for r in results.values())
    return {"success": success, "results": results}


def full_uninstall() -> dict:
    results = {}
    results["service"] = uninstall_service()
    results["firewall"] = uninstall_firewall()
    results["registry"] = remove_uninstall_registry()

    success = all(r.get("success") for r in results.values() if "error" in r)
    error_count = sum(1 for r in results.values() if not r.get("success"))
    return {"success": success, "results": results, "error_count": error_count}


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="Sentinel AI Installer")
    parser.add_argument("action", choices=["install", "uninstall", "status",
                                           "install-service", "uninstall-service",
                                           "install-firewall", "uninstall-firewall",
                                           "start", "stop"],
                        help="Action to perform")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    if args.action == "install":
        result = full_install()
    elif args.action == "uninstall":
        result = full_uninstall()
    elif args.action == "status":
        result = service_status()
    elif args.action == "install-service":
        result = install_service()
    elif args.action == "uninstall-service":
        result = uninstall_service()
    elif args.action == "install-firewall":
        result = install_firewall()
    elif args.action == "uninstall-firewall":
        result = uninstall_firewall()
    elif args.action == "start":
        result = start_service()
    elif args.action == "stop":
        result = stop_service_cmd()
    else:
        result = {"success": False, "error": "Unknown action"}

    if result.get("success"):
        print(result.get("message", "OK"))
        if "results" in result:
            for k, v in result["results"].items():
                status = "\u2713" if v.get("success") else "\u2717"
                print(f"  {status} {k}: {v.get('message', v.get('error', '?'))}")
        sys.exit(0)
    else:
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
