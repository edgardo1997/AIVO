"""Process isolation and validated IPC for untrusted Sentinel plugins."""

from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import psutil


HOOKS = frozenset({"on_ready", "on_metrics", "on_command", "on_schedule"})
MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MEMORY_BYTES = 128 * 1024 * 1024
DEFAULT_CPU_SECONDS = 5.0


class PluginSandboxError(RuntimeError):
    pass


def _json_bytes(value: Any, limit: int) -> bytes:
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PluginSandboxError("Plugin IPC accepts JSON values only") from exc
    if len(payload) > limit:
        raise PluginSandboxError("Plugin IPC message exceeds its size limit")
    return payload


def _decode_message(payload: bytes, limit: int) -> dict:
    if not isinstance(payload, bytes) or len(payload) > limit:
        raise PluginSandboxError("Invalid plugin IPC frame")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginSandboxError("Malformed plugin IPC JSON") from exc
    if not isinstance(value, dict):
        raise PluginSandboxError("Plugin IPC root must be an object")
    return value


def _sanitize_environment(plugin_dir: str) -> None:
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATH", "PATHEXT"}
    clean = {key: value for key, value in os.environ.items() if key.upper() in keep}
    clean.update({"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "SENTINEL_PLUGIN_SANDBOX": "1"})
    os.environ.clear()
    os.environ.update(clean)
    os.chdir(plugin_dir)


def _install_permission_boundary(plugin_dir: str) -> None:
    """Deny ambient OS capabilities; plugins communicate through validated hooks only."""
    plugin_root = Path(plugin_dir).resolve()
    runtime_root = Path(sys.prefix).resolve()

    def inside(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def audit(event: str, args: tuple) -> None:
        if event in {
            "subprocess.Popen", "os.system", "os.startfile", "os.startfile/2",
            "os.kill", "os.killpg",
            "socket.connect", "socket.connect_ex", "socket.bind", "socket.getaddrinfo",
            "ctypes.dlopen", "winreg.OpenKey", "winreg.CreateKey", "winreg.SetValue",
        }:
            raise PermissionError(f"Plugin capability denied: {event}")
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            target = Path(os.fsdecode(args[0])).resolve()
            if not inside(target, plugin_root) and not inside(target, runtime_root):
                raise PermissionError("Plugin file access outside its sandbox is denied")
        if event in {"os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod"} and args:
            target = Path(os.fsdecode(args[0])).resolve()
            if not inside(target, plugin_root):
                raise PermissionError("Plugin filesystem mutation outside its sandbox is denied")
        if event in {"os.listdir", "os.scandir", "os.chdir"} and args and args[0] is not None:
            target = Path(os.fsdecode(args[0])).resolve()
            if not inside(target, plugin_root) and not inside(target, runtime_root):
                raise PermissionError("Plugin directory access outside its sandbox is denied")

    sys.addaudithook(audit)


def _worker(connection, plugin_id: str, main_path: str) -> None:
    try:
        plugin_dir = str(Path(main_path).resolve().parent)
        _sanitize_environment(plugin_dir)
        _install_permission_boundary(plugin_dir)
        spec = importlib.util.spec_from_file_location(f"sentinel_sandbox_{plugin_id}", main_path)
        if not spec or not spec.loader:
            raise PluginSandboxError("Plugin module cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        hooks = {name: getattr(module, name) for name in HOOKS if callable(getattr(module, name, None))}
        connection.send_bytes(_json_bytes({"type": "ready", "hooks": sorted(hooks)}, MAX_RESPONSE_BYTES))
        while True:
            message = _decode_message(connection.recv_bytes(MAX_REQUEST_BYTES + 1), MAX_REQUEST_BYTES)
            if message.get("type") == "shutdown":
                break
            if message.get("type") != "call" or message.get("hook") not in HOOKS:
                raise PluginSandboxError("Unsupported plugin IPC operation")
            hook_name = message["hook"]
            if hook_name not in hooks:
                connection.send_bytes(_json_bytes({"ok": False, "error": "Hook is not registered"}, MAX_RESPONSE_BYTES))
                continue
            args = message.get("args", [])
            kwargs = message.get("kwargs", {})
            if not isinstance(args, list) or not isinstance(kwargs, dict):
                raise PluginSandboxError("Invalid hook arguments")
            try:
                result = hooks[hook_name](*args, **kwargs)
                response = {"ok": True, "result": result}
            except Exception as exc:
                response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            connection.send_bytes(_json_bytes(response, MAX_RESPONSE_BYTES))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send_bytes(_json_bytes({"type": "fatal", "error": f"{type(exc).__name__}: {exc}"}, MAX_RESPONSE_BYTES))
        except Exception:
            pass
    finally:
        connection.close()


class PluginSandbox:
    def __init__(self, plugin_id: str, main_path: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 memory_bytes: int = DEFAULT_MEMORY_BYTES, cpu_seconds: float = DEFAULT_CPU_SECONDS):
        self.plugin_id = plugin_id
        self.main_path = str(Path(main_path).resolve())
        self.timeout = max(0.1, min(float(timeout), 30.0))
        self.memory_bytes = max(16 * 1024 * 1024, int(memory_bytes))
        self.cpu_seconds = max(0.25, float(cpu_seconds))
        self.hooks: list[str] = []
        self._lock = threading.Lock()
        self._process = None
        self._connection = None

    @property
    def alive(self) -> bool:
        return bool(self._process and self._process.is_alive())

    def start(self) -> list[str]:
        if self.alive:
            return self.hooks
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(target=_worker, args=(child, self.plugin_id, self.main_path),
                                  name=f"sentinel-plugin-{self.plugin_id}", daemon=True)
        process.start()
        child.close()
        self._process, self._connection = process, parent
        message = self._receive_with_limits(self.timeout)
        if message.get("type") != "ready" or not isinstance(message.get("hooks"), list):
            self.stop()
            raise PluginSandboxError(message.get("error", "Plugin failed its startup handshake"))
        hooks = message["hooks"]
        if any(name not in HOOKS for name in hooks):
            self.stop()
            raise PluginSandboxError("Plugin advertised an invalid hook")
        self.hooks = hooks
        return hooks

    def _receive_with_limits(self, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        proc = psutil.Process(self._process.pid)
        initial_cpu = sum(proc.cpu_times()[:2])
        while time.monotonic() < deadline:
            if not self.alive:
                raise PluginSandboxError("Plugin process exited unexpectedly")
            try:
                if proc.children(recursive=True):
                    self.stop()
                    raise PluginSandboxError("Plugin attempted to create a child process")
                if proc.memory_info().rss > self.memory_bytes:
                    self.stop()
                    raise PluginSandboxError("Plugin exceeded its memory quota")
                if sum(proc.cpu_times()[:2]) - initial_cpu > self.cpu_seconds:
                    self.stop()
                    raise PluginSandboxError("Plugin exceeded its CPU quota")
            except psutil.NoSuchProcess as exc:
                raise PluginSandboxError("Plugin process disappeared") from exc
            if self._connection.poll(0.02):
                return _decode_message(self._connection.recv_bytes(MAX_RESPONSE_BYTES + 1), MAX_RESPONSE_BYTES)
        self.stop()
        raise PluginSandboxError("Plugin hook timed out")

    def call(self, hook: str, *args, **kwargs):
        if hook not in self.hooks or hook not in HOOKS:
            raise PluginSandboxError("Hook is not registered")
        request = _json_bytes({"type": "call", "hook": hook, "args": list(args), "kwargs": kwargs}, MAX_REQUEST_BYTES)
        with self._lock:
            if not self.alive:
                raise PluginSandboxError("Plugin process is not running")
            self._connection.send_bytes(request)
            response = self._receive_with_limits(self.timeout)
        if response.get("ok") is not True:
            raise PluginSandboxError(str(response.get("error", "Plugin hook failed")))
        return response.get("result")

    def stop(self) -> None:
        process, connection = self._process, self._connection
        self._process = self._connection = None
        if connection:
            try:
                connection.send_bytes(_json_bytes({"type": "shutdown"}, MAX_REQUEST_BYTES))
            except Exception:
                pass
            connection.close()
        if process:
            process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
