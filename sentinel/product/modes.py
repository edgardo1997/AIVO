"""Unified product modes for Sentinel Desktop.

The complexity of the runtime (IntentEngine, ToolGateway, PolicyEngine,
ModelRouter) stays behind. The user only thinks in terms of *modes*:
Developer, Gaming, Work, Privacy and Performance.

Every activation snapshots the previous system state so that the user can
always roll back. Activation applies platform changes through a pluggable
``applier`` (defaults to the real power/gpu managers on Windows, no-ops
elsewhere) so the service stays deterministic and testable in isolation.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

MODE_IDS = ("developer", "gaming", "work", "privacy", "performance")


def _default_applier() -> Callable[[str], List[str]]:
    """Build a best-effort platform applier for the current OS."""
    import platform

    if platform.system() != "Windows":
        return lambda _mode_id: []

    def apply(mode_id: str) -> List[str]:
        actions: List[str] = []

        def _power(plan: str) -> None:
            try:
                from sentinel.core import power_manager

                result = power_manager.set_active_plan(plan)
                if result and getattr(result, "success", False):
                    actions.append(f"power_plan={plan}")
            except Exception:
                log.debug("power plan apply failed for %s", mode_id, exc_info=True)

        def _gpu(profile: str) -> None:
            try:
                from sentinel.core import gpu_manager

                result = gpu_manager.set_gpu_profile(profile)
                if result and getattr(result, "success", False):
                    actions.append(f"gpu_profile={profile}")
            except Exception:
                log.debug("gpu profile apply failed for %s", mode_id, exc_info=True)

        plans = {
            "developer": "balanced",
            "gaming": "ultimate",
            "work": "balanced",
            "privacy": "power_saver",
            "performance": "high_performance",
        }
        gpus = {
            "developer": "default",
            "gaming": "gaming",
            "work": "default",
            "privacy": "power_saver",
            "performance": "max_performance",
        }
        plan = plans.get(mode_id)
        if plan:
            _power(plan)
        gpu = gpus.get(mode_id)
        if gpu:
            _gpu(gpu)
        return actions

    return apply


# --- Static mode catalog -------------------------------------------------


def build_mode_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "id": "developer",
            "name": "Developer Mode",
            "short": "Desarrollador",
            "icon": "</>",
            "description": "Optimiza Sentinel para programar: prioriza modelos de código, amplía contexto y expone herramientas técnicas.",
            "capabilities": ["VS Code", "Terminal", "Git", "Python", "Docker", "Testing"],
            "model_priority": "coding",
            "power": "balanced",
            "primary_color": "#4f8cff",
        },
        {
            "id": "gaming",
            "name": "Gaming Mode",
            "short": "Juego",
            "icon": "▶",
            "description": "Libera recursos para tus juegos: detecta juegos activos, eleva la GPU y cierra procesos seguros. Siempre con respaldo del estado anterior.",
            "capabilities": ["Detectar juego", "Prioridad GPU", "RAM disponible", "Cerrar procesos seguros", "Rollback automático"],
            "model_priority": "fast",
            "power": "ultimate",
            "primary_color": "#ff5d73",
        },
        {
            "id": "work",
            "name": "Work Mode",
            "short": "Trabajo",
            "icon": "◈",
            "description": "Prepara tu entorno profesional: correo, documentos, navegador, calendario y herramientas de trabajo.",
            "capabilities": ["Correo", "Documentos", "Navegador", "Herramientas de trabajo", "Calendario"],
            "model_priority": "quality",
            "power": "balanced",
            "primary_color": "#57c8e8",
        },
        {
            "id": "privacy",
            "name": "Privacy Mode",
            "short": "Privacidad",
            "icon": "◇",
            "description": "Control máximo de privacidad: bloquea telemetría, prefiere modelos locales y reduce conexiones externas.",
            "capabilities": ["Bloquear telemetría", "Modelos locales", "Reducir conexiones externas", "Auditar permisos"],
            "model_priority": "local",
            "power": "power_saver",
            "primary_color": "#8c7bff",
        },
        {
            "id": "performance",
            "name": "Performance Mode",
            "short": "Rendimiento",
            "icon": "▲",
            "description": "Máximo rendimiento: analiza CPU, RAM, GPU y servicios para aplicar optimización segura con respaldo.",
            "capabilities": ["Análisis CPU/RAM/GPU", "Optimización segura", "Limpieza", "Configuración avanzada"],
            "model_priority": "speed",
            "power": "high_performance",
            "primary_color": "#69d394",
        },
    ]


# --- Service ---------------------------------------------------------------


class _StateSnapshot:
    __slots__ = ("mode_id", "model_priority", "power", "ts")

    def __init__(self, mode_id: str, model_priority: str, power: str, ts: float) -> None:
        self.mode_id = mode_id
        self.model_priority = model_priority
        self.power = power
        self.ts = ts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode_id": self.mode_id,
            "model_priority": self.model_priority,
            "power": self.power,
            "ts": self.ts,
        }


class ModesService:
    """Owns the active product mode, its history and rollback snapshots."""

    def __init__(
        self,
        storage: Optional[Any] = None,
        applier: Optional[Callable[[str], List[str]]] = None,
        catalog: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._storage = storage
        self._applier = applier or _default_applier()
        self._catalog = catalog if catalog is not None else build_mode_catalog()
        self._by_id = {mode["id"]: mode for mode in self._catalog}
        self._active_mode: Optional[str] = None
        self._history: List[_StateSnapshot] = []
        self._last_actions: List[str] = []
        self._restore_catalog()

    # --- persistence helpers ---

    def _restore_catalog(self) -> None:
        if self._storage is None:
            return
        try:
            state = self._storage.config_get_json("product_modes", {})
        except Exception:
            state = {}
        active = state.get("active_mode")
        if active in self._by_id:
            self._active_mode = active
        for snapshot in state.get("history", [])[-10:]:
            if isinstance(snapshot, dict) and snapshot.get("mode_id") in self._by_id:
                self._history.append(
                    _StateSnapshot(
                        snapshot["mode_id"],
                        snapshot.get("model_priority", ""),
                        snapshot.get("power", ""),
                        float(snapshot.get("ts", 0.0)),
                    )
                )

    def _persist(self) -> None:
        if self._storage is None:
            return
        try:
            self._storage.config_set_json(
                "product_modes",
                {
                    "active_mode": self._active_mode,
                    "history": [s.to_dict() for s in self._history[-10:]],
                },
            )
        except Exception:
            log.debug("failed to persist product modes", exc_info=True)

    # --- public API ---

    def list_modes(self) -> List[Dict[str, Any]]:
        return [
            {
                **mode,
                "active": mode["id"] == self._active_mode,
                "model_priority": self.model_priority() if mode["id"] == self._active_mode else mode["model_priority"],
            }
            for mode in self._catalog
        ]

    def status(self) -> Dict[str, Any]:
        active = self._active_mode
        return {
            "active_mode": active,
            "active": self._by_id.get(active) if active else None,
            "last_actions": list(self._last_actions),
            "history": [s.to_dict() for s in self._history],
            "rollback_available": len(self._history) > 0,
            "model_priority": self.model_priority(),
        }

    def model_priority(self) -> str:
        active = self._active_mode
        if not active:
            return "balanced"
        return self._by_id[active].get("model_priority", "balanced")

    def activate(self, mode_id: str, reason: str = "", _platform_apply: bool = True) -> Dict[str, Any]:
        if mode_id not in self._by_id:
            return {"success": False, "error": f"Modo desconocido: {mode_id}", "mode_id": mode_id}
        previous = self._active_mode
        if previous and previous != mode_id:
            self._snapshot(previous)
        elif previous == mode_id:
            return {"success": True, "mode_id": mode_id, "actions": list(self._last_actions), "already_active": True}

        self._active_mode = mode_id
        self._last_actions = self._applier(mode_id) if _platform_apply else []
        self._persist()
        return {
            "success": True,
            "mode_id": mode_id,
            "previous": previous,
            "actions": list(self._last_actions),
            "reason": reason,
        }

    def deactivate(self, reason: str = "") -> Dict[str, Any]:
        active = self._active_mode
        if not active:
            return {"success": True, "mode_id": None, "actions": [], "already_inactive": True}
        self._snapshot(active)
        self._active_mode = None
        self._last_actions = self._applier("balanced") if active != "privacy" else self._applier("privacy")
        self._persist()
        return {"success": True, "mode_id": None, "previous": active, "actions": list(self._last_actions), "reason": reason}

    def rollback(self) -> Dict[str, Any]:
        if not self._history:
            return {"success": False, "error": "No hay un estado anterior que restaurar", "rollback_available": False}
        snapshot = self._history.pop()
        target = snapshot.mode_id
        self._active_mode = target
        self._last_actions = self._applier(target)
        self._persist()
        return {
            "success": True,
            "mode_id": target,
            "restored": snapshot.to_dict(),
            "actions": list(self._last_actions),
            "rollback_available": len(self._history) > 0,
        }

    def analyze_context(self) -> Dict[str, Any]:
        """Best-effort system context for recommendations (safe reads only)."""
        context: Dict[str, Any] = {}
        try:
            from sentinel.core import process_manager

            result = process_manager.list_processes(include_system=False)
            if result and getattr(result, "success", False):
                context["processes"] = len(result.processes)
        except Exception:
            log.debug("process context unavailable", exc_info=True)
        try:
            import psutil

            context["cpu_usage"] = round(psutil.cpu_percent(interval=0.1), 1)
            context["memory_usage"] = round(psutil.virtual_memory().percent, 1)
        except Exception:
            log.debug("resource context unavailable", exc_info=True)
        return context

    def recommended_mode(self) -> Optional[str]:
        """Simple, transparent heuristic to suggest a starting mode."""
        context = self.analyze_context()
        try:
            from sentinel.core import system_optimizer

            dry = system_optimizer.optimize_dry_run()
            if dry.mode in self._by_id:
                return dry.mode
        except Exception:
            log.debug("system_optimizer dry run unavailable", exc_info=True)
        if context.get("memory_usage", 0) > 85:
            return "performance"
        return None

    def _snapshot(self, mode_id: str) -> None:
        mode = self._by_id.get(mode_id)
        self._history.append(
            _StateSnapshot(
                mode_id,
                mode.get("model_priority", "balanced") if mode else "balanced",
                mode.get("power", "balanced") if mode else "balanced",
                time.time(),
            )
        )
        self._history = self._history[-10:]
