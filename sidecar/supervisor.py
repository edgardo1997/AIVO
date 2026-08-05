"""Sidecar Supervisor — watchdog process for Sentinel FastAPI backend.

States:
  STARTING → READY → (on failure) → DEGRADED/FAILED → RESTARTING → STARTING...
"""

import logging
import os
import signal
import subprocess
import sys
import time
import json
import urllib.request
import urllib.error
from logging.handlers import RotatingFileHandler

from sentinel.security.secret_redaction import SecretRedactionFilter

SUPERVISOR_VERSION = "1.0.1"
SIDECAR_HOST = os.environ.get("SENTINEL_HOST", "127.0.0.1")
SIDECAR_PORT = int(os.environ.get("SENTINEL_PORT", "8765"))
# PID lock file to prevent duplicate supervisors.
_LOCK_DIR = os.path.join(os.path.expanduser("~"), ".sentinel", "run")
_LOCK_FILE = os.path.join(_LOCK_DIR, "supervisor.pid")
HEALTH_URL = f"http://{SIDECAR_HOST}:{SIDECAR_PORT}/api/health"
MAX_RESTARTS = int(os.environ.get("SENTINEL_MAX_RESTARTS", "10"))
RESTART_DELAY = float(os.environ.get("SENTINEL_RESTART_DELAY", "2.0"))
HEALTH_INTERVAL = float(os.environ.get("SENTINEL_HEALTH_INTERVAL", "5.0"))
STARTUP_TIMEOUT = float(os.environ.get("SENTINEL_STARTUP_TIMEOUT", "30.0"))
RESTART_BACKOFF = float(os.environ.get("SENTINEL_RESTART_BACKOFF", "2.0"))

log = logging.getLogger("sentinel.supervisor")


def _acquire_lock() -> int:
    """Write PID to lock file. Return PID if we hold the lock, or sys.exit(0) if another supervisor is running."""
    os.makedirs(_LOCK_DIR, exist_ok=True)
    my_pid = os.getpid()
    try:
        if os.path.exists(_LOCK_FILE):
            with open(_LOCK_FILE, "r") as f:
                existing = f.read().strip()
            if existing:
                try:
                    old_pid = int(existing)
                    # Verify PID is still alive AND running supervisor.py
                    try:
                        import psutil

                        p = psutil.Process(old_pid)
                        cmdline = " ".join(p.cmdline()).lower()
                        if "supervisor" in cmdline and "python" in cmdline:
                            print(f"Supervisor already running (PID {old_pid}). Exiting.")
                            sys.exit(0)
                    except ImportError:
                        # Fallback: check if alive via ctypes
                        import ctypes

                        PROCESS_QUERY_INFORMATION = 0x0400
                        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, old_pid)
                        if handle:
                            ctypes.windll.kernel32.CloseHandle(handle)
                            # Process exists but could be anything — assume stale if we reached here
                            pass
                except (ValueError, OSError):
                    pass  # stale lock file, overwrite
        with open(_LOCK_FILE, "w") as f:
            f.write(str(my_pid))
        return my_pid
    except Exception as e:
        print(f"Warning: could not acquire lock file: {e}")
        return my_pid


def _release_lock():
    try:
        if os.path.exists(_LOCK_FILE):
            with open(_LOCK_FILE, "r") as f:
                existing = f.read().strip()
            if existing == str(os.getpid()):
                os.remove(_LOCK_FILE)
    except Exception:
        pass


def _configure_logging():
    log_dir = os.environ.get(
        "SENTINEL_LOG_DIR",
        str(os.path.join(os.path.expanduser("~"), ".sentinel", "logs")),
    )
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                os.path.join(log_dir, "supervisor.log"),
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
        ],
    )
    for handler in logging.root.handlers:
        handler.addFilter(SecretRedactionFilter())
    return logging.getLogger("sentinel.supervisor")


def _find_sidecar_main() -> str:
    """Locate sidecar/main.py relative to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, "main.py")
    if os.path.isfile(candidate):
        return candidate
    candidate = os.path.join(script_dir, "sidecar", "main.py")
    if os.path.isfile(candidate):
        return candidate
    raise RuntimeError(f"Cannot find sidecar/main.py from {script_dir}")


def _health_check() -> dict:
    """Returns health dict, or {'status': 'unreachable'} on failure."""
    try:
        req = urllib.request.Request(HEALTH_URL)
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
        return {"status": "unreachable", "error": str(e)}


class SupervisorState:
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    RESTARTING = "restarting"
    STOPPED = "stopped"


class SidecarSupervisor:
    def __init__(self):
        self.state = SupervisorState.STARTING
        self.process: subprocess.Popen | None = None
        self.restart_count = 0
        self.last_crash_reason: str | None = None
        self._stop_requested = False
        self._main_path = _find_sidecar_main()
        self._project_root = os.path.abspath(os.path.join(os.path.dirname(self._main_path), ".."))

    def _build_cmd(self) -> list[str]:
        return [
            sys.executable,
            "-u",
            "-m",
            "uvicorn",
            "sidecar.main:app",
            "--host",
            SIDECAR_HOST,
            "--port",
            str(SIDECAR_PORT),
            "--loop",
            "asyncio",
            "--log-level",
            "info",
        ]

    def _start_process(self) -> None:
        env = os.environ.copy()
        sidecar_dir = os.path.dirname(self._main_path)
        for p in (sidecar_dir, self._project_root):
            if p not in env.get("PYTHONPATH", ""):
                env["PYTHONPATH"] = f"{p};{env.get('PYTHONPATH', '')}"
        cmd = self._build_cmd()
        log.info("Starting sidecar: %s", " ".join(cmd))
        self.process = subprocess.Popen(
            cmd,
            cwd=self._project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.state = SupervisorState.STARTING
        # Start a daemon thread to drain stdout so the subprocess does not block on its pipe buffer
        import threading as _t

        _t.Thread(target=self._log_process_output, args=(self.process,), daemon=True).start()

    def _wait_ready(self, timeout: float) -> bool:
        deadline = time.time() + timeout
        time.sleep(1.0)  # Give the subprocess time to start uvicorn
        while time.time() < deadline:
            health = _health_check()
            if health.get("status") in ("healthy", "degraded"):
                self.state = SupervisorState.READY if health["status"] == "healthy" else SupervisorState.DEGRADED
                log.info("Sidecar %s (health: %s)", self.state, health.get("status"))
                return True
            if self.process and self.process.poll() is not None:
                return False
            time.sleep(0.5)
        return False

    def _log_process_output(self, proc) -> None:
        """Read stdout from *proc* until EOF, forwarding to the supervisor log."""
        if proc and proc.stdout:
            try:
                for line in proc.stdout:
                    log.info("[sidecar] %s", line.decode("utf-8", errors="replace").rstrip())
            except Exception:
                pass

    def _monitor_loop(self) -> None:
        while not self._stop_requested:
            if self.process is None or self.process.poll() is not None:
                if self.process and self.process.poll() is not None:
                    rc = self.process.returncode
                    self.last_crash_reason = f"exit code {rc}"
                    log.warning("Sidecar exited (code %d). Restarting...", rc)
                else:
                    self.last_crash_reason = "process not running"
                    log.warning("Sidecar process vanished. Restarting...")
                self.restart_count += 1
                if self.restart_count > MAX_RESTARTS:
                    self.state = SupervisorState.FAILED
                    log.critical("Max restarts (%d) exceeded. Giving up.", MAX_RESTARTS)
                    break
                self.state = SupervisorState.RESTARTING
                delay = min(RESTART_DELAY * (RESTART_BACKOFF ** (self.restart_count - 1)), 30.0)
                log.info("Restart attempt %d/%d in %.1fs...", self.restart_count, MAX_RESTARTS, delay)
                time.sleep(delay)
                self._start_process()
                # Wait up to STARTUP_TIMEOUT for the process to become healthy.
                # If it times out but the process is still running, do NOT kill it —
                # just keep monitoring (the next health poll will try again).
                became_ready = self._wait_ready(STARTUP_TIMEOUT)
                if not became_ready and self.process and self.process.poll() is None:
                    log.warning("Sidecar still starting after %.0fs — will keep waiting", STARTUP_TIMEOUT)
                elif not became_ready:
                    # process died during startup window
                    continue
            health = _health_check()
            if health.get("status") == "failed":
                self.state = SupervisorState.FAILED
                log.critical("Health reports 'failed' state. Stopping supervisor.")
                break
            elif health.get("status") == "unreachable":
                # If the process has exited since we last checked, restart it
                if self.process and self.process.poll() is not None:
                    continue  # will be caught at top of loop
                log.warning(
                    "Health check unreachable (process PID %s still running). Retrying in %ds...",
                    self.process.pid if self.process else "?",
                    HEALTH_INTERVAL,
                )
                time.sleep(HEALTH_INTERVAL)
                continue
            elif health.get("status") == "degraded":
                self.state = SupervisorState.DEGRADED
                missing = [
                    k for k in ("database", "gateway", "router") if health.get(k) in ("disconnected", "unavailable")
                ]
                log.warning("Sidecar degraded: %s missing", ", ".join(missing))
            else:
                self.state = SupervisorState.READY
            time.sleep(HEALTH_INTERVAL)

    def run(self) -> None:
        log.info("Sentinel Sidecar Supervisor v%s starting", SUPERVISOR_VERSION)
        self._start_process()
        if self._wait_ready(STARTUP_TIMEOUT):
            log.info("Sidecar ready on %s:%d", SIDECAR_HOST, SIDECAR_PORT)
        else:
            log.warning("Sidecar did not become ready within %.0fs — monitoring anyway", STARTUP_TIMEOUT)
        try:
            self._monitor_loop()
        except KeyboardInterrupt:
            log.info("Supervisor stopping (Ctrl+C)")
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop_requested = True
        self.state = SupervisorState.STOPPED
        if self.process and self.process.poll() is None:
            log.info("Stopping sidecar (PID %d)...", self.process.pid)
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning("Sidecar did not terminate gracefully — killing")
                self.process.kill()
                self.process.wait()
        log.info("Supervisor stopped (restarts: %d, last crash: %s)", self.restart_count, self.last_crash_reason)


def main():
    _configure_logging()
    _acquire_lock()
    supervisor = SidecarSupervisor()
    try:
        supervisor.run()
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
