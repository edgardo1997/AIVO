import logging
import threading
from fastapi import APIRouter, HTTPException
from services.plugins_service import PluginsService, PLUGIN_TEMPLATES

log = logging.getLogger("sentinel.plugins")
router = APIRouter()

# Module-level shared state
ACTIVE_PLUGINS: dict = {}
PLUGIN_METADATA: dict = {}
PLUGIN_STATES: dict = {}
_state_lock = threading.RLock()

# Service wired with module-level state
_svc = PluginsService(
    active_plugins=ACTIVE_PLUGINS,
    plugin_metadata=PLUGIN_METADATA,
    plugin_states=PLUGIN_STATES,
    state_lock=_state_lock,
)

# Re-exports for backward compatibility
PLUGIN_DIR = _svc.plugin_dir
run_hook = _svc.run_hook
discover_plugins = _svc.discover
ensure_dirs = _svc.ensure_dirs


@router.get("/list")
def list_plugins():
    return _svc.list_all()


@router.get("/templates")
def list_templates():
    return _svc.list_templates()


@router.post("/create")
def create_plugin(data: dict):
    return _svc.create(data.get("name", "my_plugin"), data.get("template", "minimal"))


@router.post("/{plugin_id}/load")
def load_plugin_endpoint(plugin_id: str):
    _svc.refresh_metadata()
    if not _svc.has_plugin(plugin_id):
        raise HTTPException(404, f"Plugin '{plugin_id}' not found")
    result = _svc.load(plugin_id)
    if result:
        return {"status": "loaded", "hooks": result["hooks"]}
    error = _svc.get_state_error(plugin_id)
    return {"status": "error", "error": error}


@router.post("/{plugin_id}/unload")
def unload_plugin_endpoint(plugin_id: str):
    _svc.unload(plugin_id)
    return {"status": "unloaded"}


@router.post("/{plugin_id}/reload")
def reload_plugin_endpoint(plugin_id: str):
    result = _svc.reload(plugin_id)
    if result:
        return {"status": "reloaded", "hooks": result["hooks"]}
    error = _svc.get_state_error(plugin_id)
    return {"status": "error", "error": error}


@router.post("/{plugin_id}/toggle")
def toggle_plugin(plugin_id: str):
    return _svc.toggle(plugin_id)


@router.get("/{plugin_id}/hooks")
def get_hooks(plugin_id: str):
    return _svc.get_hooks(plugin_id)


@router.post("/hooks/run/{hook}")
def run_system_hook(hook: str, data: dict = {}):
    results = _svc.run_hook(hook, **data)
    return {"hook": hook, "results": results}


@router.get("/states")
def get_all_states():
    return _svc.get_states()
