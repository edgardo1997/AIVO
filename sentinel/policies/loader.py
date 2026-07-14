import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .schema import validate_policy, POLICY_SCHEMA

# Sub-schemas for individual policy files
DESTRUCTIVE_PATTERNS_SCHEMA = {
    "destructive_patterns": POLICY_SCHEMA["destructive_patterns"],
}

SECURITY_SCHEMA = {
    k: v for k, v in POLICY_SCHEMA.items()
    if k in ("permission_levels", "dangerous_tools", "critical_paths",
             "emergency_stop", "tool_permissions")
}

logger = logging.getLogger(__name__)

POLICY_DIR = Path(os.path.expanduser("~/.sentinel/policies"))
POLICY_DIR.mkdir(parents=True, exist_ok=True)
try:
    try:
        from windows_acl import protect_path
    except ImportError:
        from sidecar.windows_acl import protect_path
    protect_path(POLICY_DIR, directory=True)
except ImportError:
    pass


class PolicyLoadError(Exception):
    pass


class PolicyStore:
    _instance: Optional["PolicyStore"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._mtimes: Dict[str, float] = {}
        self._callbacks: List[Callable] = []
        self._watch_thread: Optional[threading.Thread] = None
        self._stop_watch = threading.Event()

    @classmethod
    def get_instance(cls) -> "PolicyStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get(self, key: str) -> Any:
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def on_reload(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    def _notify(self) -> None:
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Policy reload callback failed: %s", e)

    def start_watching(self, interval: float = 5.0) -> None:
        if self._watch_thread and self._watch_thread.is_alive():
            return

        def _watch():
            while not self._stop_watch.is_set():
                self._stop_watch.wait(interval)
                changed = False
                for path_str, mtime in list(self._mtimes.items()):
                    p = Path(path_str)
                    if p.exists() and p.stat().st_mtime != mtime:
                        logger.info("Policy file changed: %s", path_str)
                        changed = True
                        self._mtimes[path_str] = p.stat().st_mtime
                if changed:
                    self._notify()

        self._stop_watch.clear()
        self._watch_thread = threading.Thread(target=_watch, daemon=True, name="policy-watcher")
        self._watch_thread.start()
        logger.info("Policy hot-reload watcher started (interval=%.1fs)", interval)

    def stop_watching(self) -> None:
        self._stop_watch.set()


def resolve_policy_path(filename: str) -> Path:
    path = Path(filename)
    if path.is_absolute():
        return path
    return POLICY_DIR / filename


def load_yaml_policy(filename: str, schema: Optional[Dict] = None) -> Dict[str, Any]:
    path = resolve_policy_path(filename)

    if not path.exists():
        raise PolicyLoadError(f"Policy file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PolicyLoadError(f"YAML parse error in {path}: {e}") from e

    if not isinstance(data, dict):
        raise PolicyLoadError(f"Policy file {path} must contain a top-level mapping")

    effective_schema = schema
    if effective_schema is None:
        stem = path.stem
        if stem == "destructive_patterns":
            effective_schema = DESTRUCTIVE_PATTERNS_SCHEMA
        elif stem == "security":
            effective_schema = SECURITY_SCHEMA
        else:
            effective_schema = POLICY_SCHEMA

    errors = validate_policy(data, effective_schema)
    if errors:
        raise PolicyLoadError(f"Policy validation failed for {path}:\n  " + "\n  ".join(errors))

    store = PolicyStore.get_instance()
    store._mtimes[str(path)] = path.stat().st_mtime
    store.set(path.stem, data)

    logger.info("Loaded policy: %s (%d keys)", path.stem, len(data))
    return data


def load_or_default(filename: str, default_factory: Callable, schema: Optional[Dict] = None) -> Dict[str, Any]:
    try:
        return load_yaml_policy(filename, schema)
    except PolicyLoadError as e:
        logger.warning("Could not load %s, using defaults: %s", filename, e)
        data = default_factory()
        store = PolicyStore.get_instance()
        store.set(Path(filename).stem, data)
        return data
