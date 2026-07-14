import json
import logging
import os
import sys
import importlib.util
import re
from pydantic import BaseModel

log = logging.getLogger("sentinel.plugins_service")

BUILTIN_PLUGINS_DIR = os.path.join(os.path.dirname(__file__), "..", "plugins")
PLUGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

PLUGIN_TEMPLATES = {
    "minimal": {
        "manifest.json": json.dumps({"id": "my_plugin", "name": "My Plugin", "version": "1.0.0", "author": "You", "description": "My first AIVO plugin", "hooks": ["on_ready"], "enabled": True}, indent=2),
        "main.py": "def on_ready(ctx):\n    print(f\"Plugin {ctx['plugin_id']} is ready!\")\n",
    },
    "system_health": {
        "manifest.json": json.dumps({"id": "system_health", "name": "System Health", "version": "1.0.0", "author": "AIVO", "description": "Custom system health checks and custom alerts", "hooks": ["on_metrics", "on_schedule"], "enabled": True}, indent=2),
        "main.py": "import psutil\n\ndef on_metrics(ctx):\n    cpu = ctx.get('cpu', {}).get('percent', 0)\n    mem = ctx.get('memory', {}).get('percent', 0)\n    alerts = []\n    if cpu > 90:\n        alerts.append({'type': 'cpu', 'severity': 'critical', 'message': f'CPU at {cpu}%'})\n    if mem > 95:\n        alerts.append({'type': 'memory', 'severity': 'critical', 'message': f'RAM at {mem}%'})\n    return {'alerts': alerts}\n\ndef on_schedule(ctx):\n    return {'status': 'health_check_ok'}\n",
    },
    "media_control": {
        "manifest.json": json.dumps({"id": "media_control", "name": "Media Control", "version": "1.0.0", "author": "AIVO", "description": "Control media playback via commands", "hooks": ["on_command"], "enabled": True}, indent=2),
        "main.py": "import subprocess\n\ndef on_command(ctx):\n    cmd = ctx.get('command', '').lower()\n    if 'play' in cmd or 'pause' in cmd or 'next' in cmd or 'prev' in cmd or 'volume' in cmd:\n        mapping = {\n            'play': 'play', 'pause': 'pause', 'next': 'next', 'prev': 'prev',\n            'volume up': 'volup', 'volume down': 'voldown', 'mute': 'volm',\n        }\n        for key, nircmd in mapping.items():\n            if key in cmd or key.split()[0] in cmd:\n                subprocess.run(['nircmd.exe', nircmd], capture_output=True, shell=False, timeout=5)\n                return {'handled': True, 'action': nircmd}\n    return {'handled': False}\n",
    },
}

class PluginManifest(BaseModel):
    id: str
    name: str
    version: str
    author: str = "unknown"
    description: str = ""
    hooks: list[str] = []
    enabled: bool = True

class PluginsService:
    def __init__(self, plugin_dir: str = None, active_plugins: dict = None,
                 plugin_metadata: dict = None, plugin_states: dict = None, state_lock=None):
        self.plugin_dir = plugin_dir or os.environ.get("SENTINEL_PLUGIN_DIR") or os.path.expanduser("~/.aivo/plugins")
        self._active = active_plugins if active_plugins is not None else {}
        self._metadata = plugin_metadata if plugin_metadata is not None else {}
        self._states = plugin_states if plugin_states is not None else {}
        self._lock = state_lock

    @property
    def active_plugins(self) -> dict:
        return self._active

    @property
    def plugin_metadata(self) -> dict:
        return self._metadata

    @property
    def plugin_states(self) -> dict:
        return self._states

    def ensure_dirs(self):
        os.makedirs(self.plugin_dir, exist_ok=True)
        os.makedirs(BUILTIN_PLUGINS_DIR, exist_ok=True)

    @staticmethod
    def _validate_plugin_id(plugin_id: str) -> str:
        if not isinstance(plugin_id, str) or not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            from fastapi import HTTPException
            raise HTTPException(400, "Invalid plugin identifier")
        return plugin_id

    def discover(self) -> dict:
        self.ensure_dirs()
        plugins = {}
        for base_dir in [BUILTIN_PLUGINS_DIR, self.plugin_dir]:
            if not os.path.isdir(base_dir):
                continue
            for entry in os.listdir(base_dir):
                plugin_path = os.path.join(base_dir, entry)
                manifest_path = os.path.join(plugin_path, "manifest.json")
                main_path = os.path.join(plugin_path, "main.py")
                if os.path.isdir(plugin_path) and os.path.isfile(manifest_path):
                    try:
                        with open(manifest_path) as f:
                            manifest = PluginManifest(**json.load(f))
                        manifest.id = entry
                        plugins[entry] = {"path": plugin_path, "manifest": manifest, "has_code": os.path.isfile(main_path)}
                    except Exception as e:
                        plugins[entry] = {"path": plugin_path, "error": str(e)}
        return plugins

    def load(self, plugin_id: str) -> dict | None:
        self._validate_plugin_id(plugin_id)
        info = self._metadata.get(plugin_id)
        if not info or not info.get("has_code"):
            return None
        plugin_path = os.path.realpath(info["path"])
        builtin_root = os.path.realpath(BUILTIN_PLUGINS_DIR)
        is_builtin = os.path.commonpath([plugin_path, builtin_root]) == builtin_root
        main_path = os.path.join(info["path"], "main.py")
        try:
            if not is_builtin:
                from services.plugin_sandbox import PluginSandbox
                sandbox = PluginSandbox(
                    plugin_id,
                    main_path,
                    timeout=float(os.environ.get("SENTINEL_PLUGIN_TIMEOUT_SECONDS", "5")),
                    memory_bytes=int(os.environ.get("SENTINEL_PLUGIN_MEMORY_MB", "128")) * 1024 * 1024,
                    cpu_seconds=float(os.environ.get("SENTINEL_PLUGIN_CPU_SECONDS", "5")),
                )
                hook_names = sandbox.start()
                self._active[plugin_id] = {
                    "sandbox": sandbox,
                    "hooks": hook_names,
                    "isolated": True,
                }
                self._states[plugin_id] = {"loaded": True, "error": None, "isolated": True}
                if "on_ready" in hook_names:
                    sandbox.call("on_ready", {"plugin_id": plugin_id})
                return {"id": plugin_id, "hooks": hook_names, "isolated": True}
            spec = importlib.util.spec_from_file_location(f"aivo_plugin_{plugin_id}", main_path)
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            hooks = {}
            hook_names = ["on_ready", "on_metrics", "on_command", "on_schedule"]
            for h in hook_names:
                if hasattr(module, h) and callable(getattr(module, h)):
                    hooks[h] = getattr(module, h)
            self._active[plugin_id] = {"module": module, "hooks": hooks, "isolated": False}
            self._states[plugin_id] = {"loaded": True, "error": None, "isolated": False}
            if "on_ready" in hooks:
                try:
                    hooks["on_ready"]({"plugin_id": plugin_id})
                except Exception:
                    pass
            return {"id": plugin_id, "hooks": list(hooks.keys())}
        except Exception as e:
            active = self._active.pop(plugin_id, None)
            if active and active.get("sandbox"):
                active["sandbox"].stop()
            self._states[plugin_id] = {"loaded": False, "error": str(e)}
            return None

    def unload(self, plugin_id: str):
        if plugin_id in self._active:
            sandbox = self._active[plugin_id].get("sandbox")
            if sandbox:
                sandbox.stop()
            del self._active[plugin_id]
        self._states[plugin_id] = {"loaded": False, "error": "unloaded"}
        if f"aivo_plugin_{plugin_id}" in sys.modules:
            del sys.modules[f"aivo_plugin_{plugin_id}"]

    def reload(self, plugin_id: str):
        self.unload(plugin_id)
        return self.load(plugin_id)

    def run_hook(self, hook: str, *args, **kwargs) -> list:
        results = []
        snapshot = dict(self._active)
        for pid, info in snapshot.items():
            if hook in info["hooks"]:
                try:
                    if info.get("isolated"):
                        result = info["sandbox"].call(hook, *args, **kwargs)
                    else:
                        result = info["hooks"][hook](*args, **kwargs)
                    results.append({"plugin": pid, "result": result})
                except Exception as e:
                    if info.get("isolated"):
                        self._states[pid] = {"loaded": False, "error": str(e), "isolated": True}
                        info["sandbox"].stop()
                        self._active.pop(pid, None)
                    results.append({"plugin": pid, "error": str(e)})
        return results

    def list_all(self) -> list:
        self._metadata.update(self.discover())
        plugins = []
        for pid, info in self._metadata.items():
            state = self._states.get(pid, {"loaded": False, "error": None})
            manifest = info.get("manifest")
            plugins.append({
                "id": pid,
                "name": manifest.name if manifest else pid,
                "version": manifest.version if manifest else "0.0.0",
                "author": manifest.author if manifest else "unknown",
                "description": manifest.description if manifest else "",
                "enabled": manifest.enabled if manifest else False,
                "has_code": info.get("has_code", False),
                "loaded": state.get("loaded", False),
                "error": state.get("error"),
                "isolated": state.get("isolated", False),
                "is_builtin": info["path"].startswith(BUILTIN_PLUGINS_DIR),
            })
        return {"plugins": plugins}

    def create(self, name: str, template: str = "minimal") -> dict:
        from fastapi import HTTPException
        name = self._validate_plugin_id(name)
        root = os.path.realpath(self.plugin_dir)
        plugin_path = os.path.realpath(os.path.join(root, name))
        if os.path.commonpath([plugin_path, root]) != root:
            raise HTTPException(400, "Plugin path escapes plugin directory")
        if os.path.exists(plugin_path):
            raise HTTPException(400, f"Plugin '{name}' already exists")
        os.makedirs(plugin_path, exist_ok=True)
        files = PLUGIN_TEMPLATES.get(template, PLUGIN_TEMPLATES["minimal"])
        for filename, content in files.items():
            with open(os.path.join(plugin_path, filename), "w") as f:
                f.write(content)
        return {"status": "created", "path": plugin_path}

    def toggle(self, plugin_id: str) -> dict:
        from fastapi import HTTPException
        info = self._metadata.get(plugin_id)
        if not info:
            raise HTTPException(404)
        manifest = info.get("manifest")
        if manifest:
            manifest.enabled = not manifest.enabled
            manifest_path = os.path.join(info["path"], "manifest.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest.model_dump(), f, indent=2)
            if not manifest.enabled:
                self.unload(plugin_id)
            return {"status": "toggled", "enabled": manifest.enabled}
        return {"status": "error"}

    def get_hooks(self, plugin_id: str) -> dict:
        info = self._active.get(plugin_id)
        if not info:
            return {"loaded": False, "hooks": []}
        hooks = info["hooks"]
        return {"loaded": True, "hooks": list(hooks.keys()) if isinstance(hooks, dict) else list(hooks),
                "isolated": info.get("isolated", False)}

    def get_states(self) -> dict:
        return {"states": self._states, "active_count": len(self._active)}

    def list_templates(self) -> dict:
        return {"templates": list(PLUGIN_TEMPLATES.keys())}
