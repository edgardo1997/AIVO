"""Plugin Manager — orchestrates the plugin ecosystem.

Responsibilities (per the FASE 9 architecture): discover, validate, load,
enable, disable, update and remove plugins; gate every activation behind the
permission system; dispatch product events to active plugins; and keep the
persistent registry and trust metrics in sync.

The core of Sentinel is never modified: plugins load into their own modules
behind the SDK and only act within their granted permissions.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import time as time_mod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sentinel.plugin_sdk import (
    PERMISSION_CATALOG,
    STATE_ACTIVE,
    STATE_DEACTIVATED,
    STATE_ERROR,
    STATE_EXECUTING,
    STATE_INSTALLED,
    STATE_PERMISSION_REVIEW,
    STATE_VALIDATED,
    LifecycleError,
    PluginContext,
    PluginEvent,
    PluginEventBus,
    PluginLifecycle,
    PluginManifest,
    PluginPermissionManager,
    PluginRecord,
    PluginRegistry,
    SentinelPlugin,
    load_manifest,
    validate_plugin,
)

log = logging.getLogger(__name__)

OFFICIAL_PLUGINS_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "plugins", "official"))

DEFAULT_PLUGIN_DIR = os.environ.get("SENTINEL_PLUGIN_DIR") or os.path.expanduser("~/.aivo/plugins")

TRUST_CERTIFICATIONS = (("official", 90), ("trusted", 75), ("verified", 50), ("community", 0))


class PluginManager:
    """Lifecycle and execution manager for the plugin ecosystem."""

    def __init__(
        self,
        plugin_dir: Optional[str] = None,
        registry: Optional[PluginRegistry] = None,
        permissions: Optional[PluginPermissionManager] = None,
        bus: Optional[PluginEventBus] = None,
        runner: Optional[Callable[[SentinelPlugin, str, List[Any], Dict[str, Any]], Any]] = None,
        clock=None,
    ) -> None:
        self.plugin_dir = plugin_dir or DEFAULT_PLUGIN_DIR
        self.official_dir = OFFICIAL_PLUGINS_DIR
        self._registry = registry or PluginRegistry()
        self._permissions = permissions or PluginPermissionManager()
        self._bus = bus or PluginEventBus()
        self._runner = runner or self._default_run
        self._clock = clock or time_mod.time
        self._active: Dict[str, Dict[str, Any]] = {}
        self._lifecycles: Dict[str, PluginLifecycle] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        os.makedirs(self.plugin_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Discovery & inspection
    # ------------------------------------------------------------------ #

    def _discover_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        for raw in (self.official_dir, self.plugin_dir):
            path = Path(raw)
            if path.is_dir():
                dirs.append(path)
        return dirs

    def discover(self) -> List[Dict[str, Any]]:
        plugins: List[Dict[str, Any]] = []
        for base in self._discover_dirs():
            for entry in sorted(base.iterdir()):
                if not entry.is_dir() or not (entry / "manifest.json").is_file():
                    continue
                try:
                    manifest = load_manifest(entry)
                    plugins.append(
                        {
                            "id": manifest.id,
                            "name": manifest.name,
                            "version": manifest.version,
                            "author": manifest.author,
                            "description": manifest.description,
                            "capabilities": list(manifest.capabilities),
                            "permissions": list(manifest.permissions),
                            "events": list(manifest.events),
                            "path": str(entry),
                            "official": base.resolve() == Path(self.official_dir).resolve(),
                        }
                    )
                except Exception as exc:
                    plugins.append({"id": entry.name, "name": entry.name, "version": "?", "error": str(exc), "path": str(entry), "official": False})
        return plugins

    def list(self) -> List[Dict[str, Any]]:
        discovered = {p["id"]: p for p in self.discover()}
        records = {r.plugin_id: r for r in self._registry.list()}
        plugins: List[Dict[str, Any]] = []
        for plugin_id, info in discovered.items():
            record = records.get(plugin_id)
            lifecycle = self._lifecycles.get(plugin_id)
            plugins.append(
                {
                    "id": plugin_id,
                    "name": info.get("name", plugin_id),
                    "version": info.get("version", "?"),
                    "description": info.get("description", ""),
                    "author": info.get("author", "unknown"),
                    "capabilities": info.get("capabilities", []),
                    "permissions": info.get("permissions", []),
                    "events": info.get("events", []),
                    "official": info.get("official", False),
                    "path": info.get("path", ""),
                    "status": lifecycle.state if lifecycle else (record.status if record else "discovered"),
                    "approval_status": record.approval_status if record else "unknown",
                    "trust_score": record.trust_score if record else 0.0,
                    "certification": record.certification if record else "community",
                    "failure_count": record.failure_count if record else 0,
                    "last_execution": record.last_execution if record else None,
                    "loaded": plugin_id in self._active,
                    "error": info.get("error"),
                }
            )
        return plugins

    def inspect(self, plugin_id: str) -> Dict[str, Any]:
        path = self._locate(plugin_id)
        if path is None:
            return {"found": False, "error": f"plugin not found: {plugin_id}"}
        manifest = load_manifest(path)
        validation = validate_plugin(path, manifest)
        record = self._registry.get(plugin_id)
        return {
            "found": True,
            "manifest": manifest.to_dict(),
            "validation": validation,
            "record": record.to_dict() if record else None,
            "state": self._lifecycles[plugin_id].state if plugin_id in self._lifecycles else "discovered",
        }

    def _locate(self, plugin_id: str) -> Optional[Path]:
        for base in self._discover_dirs():
            candidate = base / plugin_id
            if candidate.is_dir() and (candidate / "manifest.json").is_file():
                return candidate
        return None

    # ------------------------------------------------------------------ #
    # Install / validate
    # ------------------------------------------------------------------ #

    def install(self, source_dir, plugin_id: Optional[str] = None) -> Dict[str, Any]:
        """Install a plugin from a directory (copied into the plugin dir)."""
        source = Path(source_dir)
        if not source.is_dir():
            return {"success": False, "error": f"source is not a directory: {source_dir}"}
        manifest = load_manifest(source)
        target_id = plugin_id or manifest.id
        manifest.id = target_id
        validation = validate_plugin(source, manifest)
        if not validation["valid"]:
            return {"success": False, "error": "; ".join(validation["issues"]), "validation": validation}
        dest = Path(self.plugin_dir) / target_id
        if dest.exists():
            return {"success": False, "error": f"plugin already installed: {target_id}"}
        shutil.copytree(source, dest)
        checksum, files = validation["info"]["checksum_sha256"], validation["info"]["files"]
        record = PluginRecord(
            plugin_id=target_id,
            name=manifest.name or target_id,
            version=manifest.version,
            status=STATE_INSTALLED,
            permissions=list(manifest.permissions),
            install_date=self._clock(),
            trust_score=self._compute_trust(manifest, failures=0, executions_ok=0),
            path=str(dest),
        )
        record.certification = self._certification_for(record.trust_score)
        self._registry.upsert(record)
        self._lifecycles[target_id] = PluginLifecycle(STATE_INSTALLED)
        self._manifests[target_id] = manifest
        return {"success": True, "id": target_id, "checksum_sha256": checksum, "files": files, "record": record.to_dict()}

    def validate(self, plugin_id: str) -> Dict[str, Any]:
        path = self._locate(plugin_id)
        if path is None:
            return {"success": False, "error": f"plugin not found: {plugin_id}"}
        manifest = load_manifest(path)
        validation = validate_plugin(path, manifest)
        if not validation["valid"]:
            return {"success": False, "error": "; ".join(validation["issues"]), "validation": validation}
        lifecycle = self._lifecycles.setdefault(plugin_id, PluginLifecycle())
        try:
            lifecycle.transition(STATE_VALIDATED)
        except LifecycleError:
            pass
        record = self._registry.get(plugin_id)
        if record is not None:
            record.status = STATE_VALIDATED
            self._registry.upsert(record)
        self._manifests[plugin_id] = manifest
        return {"success": True, "id": plugin_id, "validation": validation, "state": lifecycle.state}

    # ------------------------------------------------------------------ #
    # Permission approval & activation
    # ------------------------------------------------------------------ #

    def _move_lifecycle(self, plugin_id: str, target: str) -> PluginLifecycle:
        """Advance a plugin's lifecycle through valid intermediate states."""
        lifecycle = self._lifecycles.setdefault(plugin_id, PluginLifecycle())
        path = (STATE_INSTALLED, STATE_VALIDATED, STATE_PERMISSION_REVIEW, STATE_ACTIVE)
        if target in path:
            for state in path:
                if lifecycle.can(state):
                    lifecycle.transition(state)
                if lifecycle.state == target:
                    break
        elif lifecycle.can(target):
            lifecycle.transition(target)
        return lifecycle

    def evaluate_permissions(self, plugin_id: str) -> Dict[str, Any]:
        path = self._locate(plugin_id)
        if path is None:
            return {"success": False, "error": f"plugin not found: {plugin_id}"}
        manifest = load_manifest(path)
        return {"success": True, "id": plugin_id, **self._permissions.evaluate(manifest.permissions)}

    def approve_permissions(self, plugin_id: str, permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Record explicit user approval for the plugin's permission request."""
        path = self._locate(plugin_id)
        if path is None:
            return {"success": False, "error": f"plugin not found: {plugin_id}"}
        manifest = load_manifest(path)
        requested = set(manifest.permissions)
        if permissions is not None:
            unknown = set(permissions) - requested
            if unknown:
                return {"success": False, "error": f"cannot grant undeclared permissions: {sorted(unknown)}"}
            requested = set(permissions)
        token = self._permissions.grant(plugin_id, requested)
        self._move_lifecycle(plugin_id, STATE_PERMISSION_REVIEW)
        record = self._registry.get(plugin_id)
        if record is not None:
            record.approval_status = "approved"
            record.status = STATE_PERMISSION_REVIEW
            self._registry.upsert(record)
        return {"success": True, "id": plugin_id, "token": token.to_dict()}

    def activate(self, plugin_id: str) -> Dict[str, Any]:
        """Validate → permission-gate → load the plugin into an active state."""
        path = self._locate(plugin_id)
        if path is None:
            return {"success": False, "error": f"plugin not found: {plugin_id}"}
        manifest = load_manifest(path)
        validation = validate_plugin(path, manifest)
        if not validation["valid"]:
            return {"success": False, "error": "; ".join(validation["issues"])}

        # Permission gate first: every requested permission must be covered by
        # an approved token before the plugin is allowed to become active.
        token = self._permissions.token_for(plugin_id)
        missing = [p for p in manifest.permissions if not (token and p in token.permissions)]
        if missing:
            lifecycle = self._move_lifecycle(plugin_id, STATE_PERMISSION_REVIEW)
            record = self._registry.get(plugin_id)
            if record is not None:
                record.status = STATE_PERMISSION_REVIEW
                record.approval_status = "pending"
                self._registry.upsert(record)
            return {"success": False, "blocked": "permission_review", "missing": missing, "evaluation": self._permissions.evaluate(manifest.permissions)}

        lifecycle = self._move_lifecycle(plugin_id, STATE_ACTIVE)
        loaded = self._load_plugin(plugin_id, path, manifest)
        if not loaded["success"]:
            lifecycle.transition(STATE_ERROR)
            record = self._registry.get(plugin_id)
            if record is not None:
                record.status = STATE_ERROR
                self._registry.upsert(record)
            return loaded
        self._active[plugin_id] = loaded
        self._subscribe_events(plugin_id, loaded["events"] if isinstance(loaded.get("events"), list) else [])
        record = self._registry.get(plugin_id)
        if record is not None:
            record.status = STATE_ACTIVE
            self._registry.upsert(record)
        return {"success": True, "id": plugin_id, "hooks": loaded.get("hooks", []), "state": lifecycle.state}

    def enable(self, plugin_id: str) -> Dict[str, Any]:
        return self.activate(plugin_id)

    def disable(self, plugin_id: str) -> Dict[str, Any]:
        return self.deactivate(plugin_id)

    def deactivate(self, plugin_id: str) -> Dict[str, Any]:
        lifecycle = self._lifecycles.setdefault(plugin_id, PluginLifecycle())
        active = self._active.pop(plugin_id, None)
        if active is not None and active.get("stop"):
            try:
                active["stop"]()
            except Exception as exc:
                log.debug("plugin %s stop hook failed: %s", plugin_id, exc)
        try:
            lifecycle.transition(STATE_DEACTIVATED)
        except LifecycleError:
            lifecycle.transition(STATE_INSTALLED)
        record = self._registry.get(plugin_id)
        if record is not None:
            record.status = lifecycle.state
            self._registry.upsert(record)
        return {"success": True, "id": plugin_id, "state": lifecycle.state}

    # ------------------------------------------------------------------ #
    # Update / remove
    # ------------------------------------------------------------------ #

    def update(self, plugin_id: str, source_dir) -> Dict[str, Any]:
        path = self._locate(plugin_id)
        if path is None:
            return {"success": False, "error": f"plugin not found: {plugin_id}"}
        source = Path(source_dir)
        manifest = load_manifest(source)
        if manifest.id != plugin_id:
            return {"success": False, "error": f"source manifest id '{manifest.id}' does not match '{plugin_id}'"}
        validation = validate_plugin(source, manifest)
        if not validation["valid"]:
            return {"success": False, "error": "; ".join(validation["issues"])}
        was_active = plugin_id in self._active
        if was_active:
            self.deactivate(plugin_id)
        self.remove(plugin_id)
        result = self.install(source, plugin_id=plugin_id)
        if result["success"] and was_active:
            self.activate(plugin_id)
        return result

    def remove(self, plugin_id: str) -> Dict[str, Any]:
        if plugin_id in self._active:
            self.deactivate(plugin_id)
        path = self._locate(plugin_id)
        removed = False
        if path is not None:
            shutil.rmtree(path, ignore_errors=True)
            removed = True
        self._registry.remove(plugin_id)
        self._lifecycles.pop(plugin_id, None)
        self._manifests.pop(plugin_id, None)
        self._permissions.revoke(plugin_id)
        return {"success": True, "id": plugin_id, "removed": removed}

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Dispatch a product event to all subscribed active plugins."""
        return self._bus.emit(event_type, payload, source="sentinel")

    def _subscribe_events(self, plugin_id: str, events: List[str]) -> None:
        def make_handler(pid: str):
            def handler(event_dict: Dict[str, Any]) -> Any:
                return self._dispatch(pid, PluginEvent(**event_dict))
            return handler

        for event_type in events:
            handler = make_handler(plugin_id)
            try:
                self._bus.subscribe(event_type, handler)
                self._active[plugin_id].setdefault("handlers", []).append((event_type, handler))
            except Exception as exc:
                log.debug("plugin %s could not subscribe to %s: %s", plugin_id, event_type, exc)

    def _dispatch(self, plugin_id: str, event: PluginEvent) -> Any:
        info = self._active.get(plugin_id)
        if info is None:
            return {"handled": False, "error": "not active"}
        started = self._clock()
        try:
            if info.get("instance") is not None:
                result = info["instance"].on_event(event)
            elif info.get("hooks") and "on_event" in info["hooks"]:
                result = info["hooks"]["on_event"](event.to_dict())
            else:
                return {"handled": False}
            duration_ms = (self._clock() - started) * 1000
            self._registry.touch_execution(plugin_id, ok=True, duration_ms=duration_ms, detail=f"event:{event.type}")
            return {"handled": True, "result": result}
        except Exception as exc:
            duration_ms = (self._clock() - started) * 1000
            self._registry.touch_execution(plugin_id, ok=False, duration_ms=duration_ms, detail=f"event:{event.type}")
            log.warning("plugin %s failed on event %s: %s", plugin_id, event.type, exc)
            return {"handled": False, "error": str(exc)}

    def dispatch_command(self, plugin_id: str, command: str, **kwargs: Any) -> Any:
        """Route a command to a single active plugin (used by the gateway)."""
        info = self._active.get(plugin_id)
        if info is None:
            return {"handled": False, "error": "not active"}
        started = self._clock()
        try:
            if info.get("instance") is not None:
                result = info["instance"].on_command(command, **kwargs)
            elif info.get("hooks") and "on_command" in info["hooks"]:
                result = info["hooks"]["on_command"](command, **kwargs)
            else:
                return {"handled": False}
            duration_ms = (self._clock() - started) * 1000
            self._registry.touch_execution(plugin_id, ok=True, duration_ms=duration_ms, detail=f"command:{command}")
            return {"handled": True, "result": result}
        except Exception as exc:
            duration_ms = (self._clock() - started) * 1000
            self._registry.touch_execution(plugin_id, ok=False, duration_ms=duration_ms, detail=f"command:{command}")
            return {"handled": False, "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    def _load_plugin(self, plugin_id: str, path: Path, manifest: PluginManifest) -> Dict[str, Any]:
        """Load the plugin entrypoint (SDK class preferred, legacy hooks fallback)."""
        entrypoint = path / manifest.entrypoint
        if entrypoint.is_file():
            instance = self._load_sdk_plugin(plugin_id, entrypoint, manifest)
            if instance is not None:
                context = PluginContext(plugin_id, manifest, self._permissions, emit_event=lambda ev: self._dispatch(plugin_id, ev))
                instance.context = context
                instance.plugin_id = plugin_id
                instance.manifest = manifest
                return {
                    "success": True,
                    "instance": instance,
                    "hooks": ["on_ready", "on_event", "on_command"],
                    "events": list(manifest.events),
                    "stop": instance.on_stop,
                }
        # Legacy fallback: main.py with plain hook functions.
        legacy = path / "main.py"
        if legacy.is_file():
            module = self._import_module(plugin_id, legacy)
            if module is not None:
                hooks = {name: getattr(module, name) for name in ("on_ready", "on_event", "on_command") if callable(getattr(module, name, None))}
                return {
                    "success": True,
                    "module": module,
                    "hooks": hooks,
                    "events": list(manifest.events),
                    "stop": None,
                }
        return {"success": False, "error": f"no loadable entrypoint found in {path}"}

    def _load_sdk_plugin(self, plugin_id: str, entrypoint: Path, manifest: PluginManifest) -> Optional[SentinelPlugin]:
        module = self._import_module(f"sentinel_plugin_{plugin_id}", entrypoint)
        if module is None:
            return None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, SentinelPlugin) and attr is not SentinelPlugin:
                try:
                    return attr()
                except Exception as exc:
                    log.debug("plugin %s class %s failed to construct: %s", plugin_id, attr_name, exc)
        factory = getattr(module, "create_plugin", None)
        if callable(factory):
            try:
                return factory()
            except Exception as exc:
                log.debug("plugin %s factory failed: %s", plugin_id, exc)
        return None

    @staticmethod
    def _import_module(name: str, path: Path):
        try:
            spec = importlib.util.spec_from_file_location(name, str(path))
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            log.warning("plugin import failed for %s: %s", path, exc)
            return None

    @staticmethod
    def _default_run(plugin: SentinelPlugin, action: str, args: List[Any], kwargs: Dict[str, Any]) -> Any:
        return getattr(plugin, action)(*args, **kwargs)

    # ------------------------------------------------------------------ #
    # Trust, certification & metrics
    # ------------------------------------------------------------------ #

    def _compute_trust(self, manifest: PluginManifest, failures: int, executions_ok: int) -> float:
        score = 60.0
        if manifest.checksum_sha256:
            score += 15
        if manifest.signature_ed25519 and manifest.publisher_key_id:
            score += 15
        risk_penalty = {"low": 0, "medium": -3, "high": -6, "critical": -10}
        for perm in manifest.permissions:
            score += risk_penalty.get(PERMISSION_CATALOG.get(perm, {}).get("risk", "low"), 0)
        score -= min(failures * 2, 30)
        score += min(executions_ok * 0.5, 10)
        return max(0.0, min(100.0, score))

    def _certification_for(self, trust_score: float) -> str:
        for name, threshold in TRUST_CERTIFICATIONS:
            if trust_score >= threshold:
                return name
        return "community"

    def certification_level(self, plugin_id: str) -> str:
        record = self._registry.get(plugin_id)
        return record.certification if record else "community"

    def metrics(self) -> Dict[str, Any]:
        records = self._registry.list()
        installed = len(records)
        active = len(self._active)
        failures = sum(r.failure_count for r in records)
        cert_counts: Dict[str, int] = {}
        for record in records:
            cert_counts[record.certification] = cert_counts.get(record.certification, 0) + 1
        total_calls = 0
        total_failures = 0
        total_duration_ms = 0.0
        for record in records:
            agg = self._registry.aggregate_metrics(record.plugin_id)
            total_calls += agg["calls"]
            total_failures += agg["failures"]
            total_duration_ms += agg["avg_duration_ms"] * agg["calls"]
        return {
            "installed_plugins": installed,
            "active_plugins": active,
            "plugin_failures": failures,
            "execution": {
                "calls": total_calls,
                "failures": total_failures,
                "avg_duration_ms": round(total_duration_ms / total_calls, 1) if total_calls else 0.0,
            },
            "security_violations": len(self._permissions.approvals()),
            "certifications": cert_counts,
            "plugins": [r.to_dict() for r in records],
        }
