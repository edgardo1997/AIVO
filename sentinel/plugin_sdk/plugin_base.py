"""Developer-facing base class for Sentinel plugins.

Plugin authors subclass ``SentinelPlugin`` and implement handlers. The SDK
guarantees the Sentinel core stays untouched: plugins only ever receive a
scoped ``PluginContext`` and may only act within their granted permissions.
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any, Dict, List, Optional

from .events import PluginEvent
from .manifest import PluginManifest
from .permission import PermissionDeniedError

log = logging.getLogger(__name__)


class PluginContext:
    """Scoped view of the world handed to a plugin.

    The context exposes only the capabilities the plugin was granted.
    There is deliberately no reference to the orchestrator, pipeline or
    memory core: the boundary between plugins and Sentinel stays one-way.
    """

    def __init__(
        self,
        plugin_id: str,
        manifest: PluginManifest,
        permissions: Any,
        emit_event=None,
    ) -> None:
        self.plugin_id = plugin_id
        self.manifest = manifest
        self._permissions = permissions
        self._emit_event = emit_event

    @property
    def permissions(self) -> List[str]:
        return self._permissions.approved_permissions(self.plugin_id)

    def require(self, permission: str) -> None:
        if not self._permissions.has_permission(self.plugin_id, permission):
            raise PermissionDeniedError(
                f"plugin '{self.plugin_id}' lacks permission '{permission}'"
            )

    def has(self, permission: str) -> bool:
        return self._permissions.has_permission(self.plugin_id, permission)

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self._emit_event is not None:
            self._emit_event(PluginEvent(type=event_type, payload=payload or {}, source=self.plugin_id))
        else:
            log.debug("plugin %s emitted event %s (no bus attached)", self.plugin_id, event_type)

    def tool_specs(self) -> List[Dict[str, Any]]:
        return []


class SentinelPlugin(ABC):
    """Base class for all Sentinel plugins.

    A minimal plugin:

    .. code-block:: python

        from sentinel.plugin_sdk import SentinelPlugin

        class MyPlugin(SentinelPlugin):
            def on_ready(self):
                return {"status": "ready"}

            def on_command(self, command, **kwargs):
                return {"echo": command}
    """

    #: Manifest of the plugin (injected by the manager at load time).
    manifest: PluginManifest = None

    def __init__(self, context: Optional[PluginContext] = None) -> None:
        self.context = context
        self.plugin_id = context.plugin_id if context else ""

    # --- lifecycle hooks ---

    def on_ready(self) -> Any:
        return {"status": "ready"}

    def on_stop(self) -> Any:
        return {"status": "stopped"}

    # --- event hooks ---

    def on_event(self, event: PluginEvent) -> Any:
        return None

    # --- command / tool hooks ---

    def on_command(self, command: str, **kwargs: Any) -> Any:
        return {"handled": False}

    def execute(self, action: str, **kwargs: Any) -> Any:
        """Generic entry point used by the tool gateway when tools are delegated."""
        return self.on_command(action, **kwargs)

    # --- context helpers ---

    def require(self, permission: str) -> None:
        if self.context is not None:
            self.context.require(permission)

    def has(self, permission: str) -> bool:
        return self.context is not None and self.context.has(permission)

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.context is not None:
            self.context.emit(event_type, payload)

    def tool_specs(self) -> List[Dict[str, Any]]:
        return []
