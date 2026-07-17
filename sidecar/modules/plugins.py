import json
import logging
import os
import re
import sys
import importlib.util
import inspect
import traceback
from pathlib import Path
from threading import Thread
from typing import Optional, Callable
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("aivo.plugins")

router = APIRouter()

PLUGIN_DIR = os.path.expanduser("~/.aivo/plugins")
BUILTIN_PLUGINS_DIR = os.path.join(os.path.dirname(__file__), "..", "plugins")
ACTIVE_PLUGINS: dict = {}
PLUGIN_METADATA: dict = {}
PLUGIN_STATES: dict = {}

def ensure_dirs():
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    os.makedirs(BUILTIN_PLUGINS_DIR, exist_ok=True)

class PluginManifest(BaseModel):
    id: str
    name: str
    version: str
    author: str = "unknown"
    description: str = ""
    hooks: list[str] = []
    enabled: bool = True

def discover_plugins():
    ensure_dirs()
    plugins = {}
    for base_dir in [BUILTIN_PLUGINS_DIR, PLUGIN_DIR]:
        if not os.path.isdir(base_dir):
            continue
        for entry in os.listdir(base_dir):
            plugin_dir = os.path.join(base_dir, entry)
            manifest_path = os.path.join(plugin_dir, "manifest.json")
            main_path = os.path.join(plugin_dir, "main.py")
            if os.path.isdir(plugin_dir) and os.path.isfile(manifest_path):
                try:
                    with open(manifest_path) as f:
                        manifest = PluginManifest(**json.load(f))
                    manifest.id = entry
                    plugins[entry] = {"path": plugin_dir, "manifest": manifest, "has_code": os.path.isfile(main_path)}
                except Exception as e:
                    log.warning("Failed to load manifest for plugin '%s': %s", entry, e)
                    plugins[entry] = {"path": plugin_dir, "error": str(e)}
    return plugins

def load_plugin(plugin_id: str) -> Optional[dict]:
    info = PLUGIN_METADATA.get(plugin_id)
    if not info or not info.get("has_code"):
        return None
    main_path = os.path.join(info["path"], "main.py")
    try:
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

        ACTIVE_PLUGINS[plugin_id] = {"module": module, "hooks": hooks}
        PLUGIN_STATES[plugin_id] = {"loaded": True, "error": None}

        if "on_ready" in hooks:
            try:
                hooks["on_ready"]({"plugin_id": plugin_id})
            except Exception as e:
                log.warning("Plugin '%s' on_ready hook failed: %s", plugin_id, e)
                PLUGIN_STATES[plugin_id]["on_ready_error"] = str(e)

        return {"id": plugin_id, "hooks": list(hooks.keys())}
    except Exception as e:
        log.exception("Failed to load plugin '%s': %s", plugin_id, e)
        PLUGIN_STATES[plugin_id] = {"loaded": False, "error": str(e)}
        return None

def unload_plugin(plugin_id: str):
    if plugin_id in ACTIVE_PLUGINS:
        del ACTIVE_PLUGINS[plugin_id]
    PLUGIN_STATES[plugin_id] = {"loaded": False, "error": "unloaded"}
    if plugin_id in sys.modules:
        del sys.modules[f"aivo_plugin_{plugin_id}"]

def reload_plugin(plugin_id: str):
    unload_plugin(plugin_id)
    return load_plugin(plugin_id)

def run_hook(hook: str, *args, **kwargs):
    results = []
    for pid, info in ACTIVE_PLUGINS.items():
        if hook in info["hooks"]:
            try:
                result = info["hooks"][hook](*args, **kwargs)
                results.append({"plugin": pid, "result": result})
            except Exception as e:
                results.append({"plugin": pid, "error": str(e)})
    return results

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
        "main.py": "import subprocess\n\ndef on_command(ctx):\n    cmd = ctx.get('command', '').lower()\n    if 'play' in cmd or 'pause' in cmd or 'next' in cmd or 'prev' in cmd or 'volume' in cmd:\n        mapping = {\n            'play': 'play', 'pause': 'pause', 'next': 'next', 'prev': 'prev',\n            'volume up': 'volup', 'volume down': 'voldown', 'mute': 'volm',\n        }\n        for key, nircmd in mapping.items():\n            if key in cmd or key.split()[0] in cmd:\n                subprocess.run(['nircmd.exe', nircmd], capture_output=True, shell=True)\n                return {'handled': True, 'action': nircmd}\n    return {'handled': False}\n",
    },
}

@router.get("/list")
def list_plugins():
    PLUGIN_METADATA.update(discover_plugins())
    plugins = []
    for pid, info in PLUGIN_METADATA.items():
        state = PLUGIN_STATES.get(pid, {"loaded": False, "error": None})
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
            "is_builtin": info["path"].startswith(BUILTIN_PLUGINS_DIR),
        })
    return {"plugins": plugins}

@router.post("/{plugin_id}/load")
def load_plugin_endpoint(plugin_id: str):
    PLUGIN_METADATA.update(discover_plugins())
    if plugin_id not in PLUGIN_METADATA:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found")
    result = load_plugin(plugin_id)
    if result:
        return {"status": "loaded", "hooks": result["hooks"]}
    error = PLUGIN_STATES.get(plugin_id, {}).get("error", "Unknown error")
    return {"status": "error", "error": error}

@router.post("/{plugin_id}/unload")
def unload_plugin_endpoint(plugin_id: str):
    unload_plugin(plugin_id)
    return {"status": "unloaded"}

@router.post("/{plugin_id}/reload")
def reload_plugin_endpoint(plugin_id: str):
    result = reload_plugin(plugin_id)
    if result:
        return {"status": "reloaded", "hooks": result["hooks"]}
    return {"status": "error", "error": PLUGIN_STATES.get(plugin_id, {}).get("error")}

@router.post("/{plugin_id}/toggle")
def toggle_plugin(plugin_id: str):
    info = PLUGIN_METADATA.get(plugin_id)
    if not info:
        raise HTTPException(404)
    manifest = info.get("manifest")
    if manifest:
        manifest.enabled = not manifest.enabled
        manifest_path = os.path.join(info["path"], "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest.model_dump(), f, indent=2)
        if not manifest.enabled:
            unload_plugin(plugin_id)
        return {"status": "toggled", "enabled": manifest.enabled}
    return {"status": "error"}

def _safe_plugin_name(name: str) -> str:
    # Restrict to a simple slug so the name can't traverse outside PLUGIN_DIR
    # (e.g. "../../evil") or write to arbitrary paths.
    name = os.path.basename((name or "").strip())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise HTTPException(400, "Invalid plugin name: use letters, numbers, '_' or '-' (max 64)")
    return name

@router.post("/create")
def create_plugin(data: dict):
    template = data.get("template", "minimal")
    name = _safe_plugin_name(data.get("name", "my_plugin"))
    plugin_dir = os.path.join(PLUGIN_DIR, name)
    if os.path.exists(plugin_dir):
        raise HTTPException(400, f"Plugin '{name}' already exists")
    os.makedirs(plugin_dir, exist_ok=True)
    files = PLUGIN_TEMPLATES.get(template, PLUGIN_TEMPLATES["minimal"])
    for filename, content in files.items():
        fpath = os.path.join(plugin_dir, filename)
        with open(fpath, "w") as f:
            f.write(content)
    return {"status": "created", "path": plugin_dir}

@router.get("/templates")
def list_templates():
    return {"templates": list(PLUGIN_TEMPLATES.keys())}

@router.get("/{plugin_id}/hooks")
def get_hooks(plugin_id: str):
    info = ACTIVE_PLUGINS.get(plugin_id)
    if not info:
        return {"loaded": False, "hooks": []}
    return {"loaded": True, "hooks": list(info["hooks"].keys())}

@router.post("/hooks/run/{hook}")
def run_system_hook(hook: str, data: dict = {}):
    results = run_hook(hook, **data)
    return {"hook": hook, "results": results}

@router.get("/states")
def get_all_states():
    return {"states": PLUGIN_STATES, "active_count": len(ACTIVE_PLUGINS)}
