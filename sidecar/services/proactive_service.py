import logging
import os
import threading
import time
import uuid

log = logging.getLogger("sentinel.proactive_service")

SCAN_INTERVAL = 30
AI_SCAN_INTERVAL = 120

THRESHOLDS = {
    "cpu": {"warning": 70, "critical": 90},
    "memory": {"warning": 75, "critical": 90},
    "disk": {"warning": 85, "critical": 95},
    "swap": {"warning": 50, "critical": 80},
    "processes": {"warning": 150, "critical": 250},
    "uptime_days": {"warning": 7, "critical": 30},
}

SUGGESTION_TEMPLATES = [
    {"id": "high_cpu", "icon": "\U0001F525", "priority": "warning", "title": "High CPU Usage ({value}%)",
     "message": "CPU is at {value}%. Consider closing resource-heavy applications.",
     "actions": [{"label": "Kill Top CPU Process", "action": "kill_top_cpu"}]},
    {"id": "high_memory", "icon": "\U0001F4BE", "priority": "warning", "title": "High Memory Usage ({value}%)",
     "message": "RAM usage is at {value}%. Consider freeing up memory.",
     "actions": [{"label": "Kill Top Memory Process", "action": "kill_top_mem"}]},
    {"id": "critical_memory", "icon": "\u26A0\uFE0F", "priority": "critical", "title": "Critical Memory ({value}%)",
     "message": "CRITICAL: RAM at {value}%. System may become unstable.",
     "actions": [{"label": "Kill Top Memory Process", "action": "kill_top_mem"}]},
    {"id": "high_disk", "icon": "\U0001F4C0", "priority": "warning", "title": "Disk Almost Full ({value}%)",
     "message": "Disk is at {value}% capacity. Consider cleaning up.",
     "actions": []},
    {"id": "long_uptime", "icon": "\u23F3", "priority": "info", "title": "Long Uptime ({value}d)",
     "message": "System has been running for {value} days. A reboot may help performance.",
     "actions": []},
    {"id": "high_temp", "icon": "\U0001F321\uFE0F", "priority": "warning", "title": "High Temperature ({value}\u00B0C)",
     "message": "Component temperature is high at {value}\u00B0C.",
     "actions": []},
    {"id": "many_processes", "icon": "\U0001F4CA", "priority": "info", "title": "Many Processes ({value})",
     "message": "{value} processes running. Consider closing unused apps.",
     "actions": []},
    {"id": "high_swap", "icon": "\U0001F504", "priority": "warning", "title": "High Swap Usage ({value}%)",
     "message": "Swap is at {value}%. Consider adding more RAM.",
     "actions": []},
    {"id": "ai_insight", "icon": "\U0001F9E0", "priority": "info", "title": "AI Insight Available",
     "message": "New AI analysis of your system is ready.",
     "actions": [{"label": "View Analysis", "action": "view_analysis"}]},
]

class ProactiveService:
    def __init__(self, suggestions: list = None, metrics_history: list = None,
                 engine_active: list = None, permissions_svc=None,
                 audit_svc=None, plugins_svc=None, ai_svc=None):
        self._suggestions = suggestions if suggestions is not None else []
        self._metrics_history = metrics_history if metrics_history is not None else []
        self._engine_active = engine_active if engine_active is not None else [False]
        self._perm = permissions_svc
        self._audit = audit_svc
        self._plugins = plugins_svc
        self._ai = ai_svc
        self._last_scan: float = 0
        self._last_ai_scan: float = 0
        self._engine_thread: threading.Thread | None = None
        self._stop_engine = threading.Event()

    @property
    def suggestions(self) -> list:
        return self._suggestions

    @property
    def metrics_history(self) -> list:
        return self._metrics_history

    @property
    def engine_active(self) -> bool:
        return self._engine_active[0]

    @engine_active.setter
    def engine_active(self, value: bool):
        self._engine_active[0] = value

    def set_permissions_service(self, svc):
        self._perm = svc

    def set_audit_service(self, svc):
        self._audit = svc

    def set_plugins_service(self, svc):
        self._plugins = svc

    def set_ai_service(self, svc):
        self._ai = svc

    def format_bytes(self, b: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(b) < 1024:
                return f"{b:.1f}{unit}"
            b //= 1024
        return f"{b:.1f}PB"

    def get_top_process(self, metric: str):
        import psutil
        key = "cpu_percent" if metric == "cpu" else "memory_percent"
        processes = []
        for proc in psutil.process_iter(["pid", "name", key]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not processes:
            return (0, "N/A", 0)
        top = max(processes, key=lambda p: p.get(key, 0) or 0)
        return (top.get(key, 0), top.get("name", "N/A"), top.get("pid", 0))

    def check_thresholds(self):
        import psutil
        now = time.time()
        cpu_percent = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        boot_time = psutil.boot_time()
        uptime_days = (now - boot_time) / 86400
        swap = psutil.swap_memory()
        proc_count = len(psutil.pids())

        checks = [
            ("cpu", cpu_percent),
            ("memory", mem.percent),
            ("swap", swap.percent),
        ]

        for check_id, value in checks:
            if check_id not in THRESHOLDS:
                continue
            t = THRESHOLDS[check_id]
            if value >= t["critical"]:
                self._add_or_update_suggestion(check_id, value, "critical")
            elif value >= t["warning"]:
                self._add_or_update_suggestion(check_id, value, "warning")

        if disk.percent >= THRESHOLDS["disk"]["critical"]:
            self._add_or_update_suggestion("high_disk", disk.percent, "critical")
        elif disk.percent >= THRESHOLDS["disk"]["warning"]:
            self._add_or_update_suggestion("high_disk", disk.percent, "warning")

        if uptime_days >= THRESHOLDS["uptime_days"]["critical"]:
            self._add_or_update_suggestion("long_uptime", int(uptime_days), "critical")
        elif uptime_days >= THRESHOLDS["uptime_days"]["warning"]:
            self._add_or_update_suggestion("long_uptime", int(uptime_days), "warning")

        if proc_count >= THRESHOLDS["processes"]["critical"]:
            self._add_or_update_suggestion("many_processes", proc_count, "critical")
        elif proc_count >= THRESHOLDS["processes"]["warning"]:
            self._add_or_update_suggestion("many_processes", proc_count, "warning")

        now_ts = time.time()
        if now_ts - self._last_ai_scan > AI_SCAN_INTERVAL:
            self._add_or_update_suggestion("ai_insight", 0, "info")
            self._last_ai_scan = now_ts

        stale_cutoff = now - 3600
        self._suggestions[:] = [s for s in self._suggestions if s.get("timestamp", 0) > stale_cutoff]

    def _add_or_update_suggestion(self, check_id: str, value, priority: str):
        for s in self._suggestions:
            if s.get("id") == check_id:
                s["value"] = value
                s["priority"] = priority
                s["timestamp"] = time.time()
                return
        template = None
        for t in SUGGESTION_TEMPLATES:
            if t["id"] == check_id:
                template = t
                break
        if not template:
            return
        title = template["title"].replace("{value}", str(value))
        message = template["message"].replace("{value}", str(value))
        self._suggestions.append({
            "id": check_id,
            "uid": str(uuid.uuid4())[:8],
            "title": title,
            "message": message,
            "priority": priority,
            "icon": template["icon"],
            "actions": template["actions"],
            "value": value,
            "timestamp": time.time(),
        })

    def store_metrics_snapshot(self):
        import psutil
        snapshot = {
            "timestamp": time.time(),
            "cpu": psutil.cpu_percent(interval=0.2),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("C:\\").percent,
            "processes": len(psutil.pids()),
        }
        self._metrics_history.append(snapshot)
        if len(self._metrics_history) > 60:
            self._metrics_history[:] = self._metrics_history[-60:]

    def get_trend(self) -> dict:
        if len(self._metrics_history) < 20:
            return {"reliable": False}
        oldest = self._metrics_history[:10]
        newest = self._metrics_history[-10:]
        avg_old = {k: sum(d[k] for d in oldest) / len(oldest) for k in ("cpu", "memory", "disk") if oldest}
        avg_new = {k: sum(d[k] for d in newest) / len(newest) for k in ("cpu", "memory", "disk") if newest}
        trends = {}
        for k in avg_old:
            diff = avg_new[k] - avg_old[k]
            if abs(diff) < 2:
                trends[k] = "stable"
            elif diff > 0:
                trends[k] = "up"
            else:
                trends[k] = "down"
        return {"reliable": True, "old_avg": avg_old, "new_avg": avg_new, "trends": trends}

    def run_engine(self):
        self._engine_active[0] = True
        self._last_scan = time.time()
        while not self._stop_engine.is_set():
            try:
                if self._perm:
                    perms = self._perm.repo.load()
                    if perms.get("level") == "view":
                        time.sleep(SCAN_INTERVAL)
                        continue
                self.check_thresholds()
                self.store_metrics_snapshot()
                if self._plugins:
                    self._plugins.run_hook("on_metrics", cpu={"percent": 0}, memory={"percent": 0})
                self._last_scan = time.time()
                self._try_ai_analysis()
            except Exception as e:
                log.warning("Proactive engine error: %s", e)
            self._stop_engine.wait(SCAN_INTERVAL)
        self._engine_active[0] = False

    def _try_ai_analysis(self):
        if not self._ai:
            return
        now = time.time()
        if now - self._last_ai_scan < AI_SCAN_INTERVAL:
            return
        self._last_ai_scan = now
        try:
            import psutil
            metrics = {
                "cpu": psutil.cpu_percent(interval=0.5),
                "memory": psutil.virtual_memory()._asdict(),
                "disk": psutil.disk_usage("C:\\")._asdict(),
                "load_avg": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
            }
            cfg = self._ai.repo.load()
            from services.ai_service import FREE_PROVIDERS
            provider_info = FREE_PROVIDERS.get(cfg.get("provider", ""), {})
            if cfg.get("api_key") or provider_info.get("url", "").startswith("http://localhost"):
                thread = threading.Thread(target=self._ai.analyze_metrics, args=(metrics,), daemon=True)
                thread.start()
        except Exception as e:
            log.debug("AI analysis skipped: %s", e)

    def start(self):
        if self._engine_thread and self._engine_thread.is_alive():
            return
        self._stop_engine.clear()
        self._engine_thread = threading.Thread(target=self.run_engine, daemon=True)
        self._engine_thread.start()

    def stop(self):
        self._stop_engine.set()
        self._engine_active[0] = False

    def get_suggestions(self) -> dict:
        trend = self.get_trend()
        return {"suggestions": list(self._suggestions), "trends": trend, "engine_active": self._engine_active[0]}

    def dismiss_suggestion(self, suggestion_id: str) -> dict:
        for s in self._suggestions:
            if s.get("uid") == suggestion_id or s.get("id") == suggestion_id:
                self._suggestions.remove(s)
                return {"status": "dismissed"}
        return {"status": "not_found"}

    def set_gateway(self, gw):
        self._gateway = gw

    async def execute_suggestion(self, suggestion_id: str) -> dict:
        from fastapi import HTTPException
        if not self._gateway:
            return {"status": "error", "message": "Gateway not available"}
        for s in self._suggestions:
            if s.get("uid") != suggestion_id and s.get("id") != suggestion_id:
                continue
            for action in s.get("actions", []):
                act = action.get("action", "")
                if act in ("kill_top_cpu", "kill_top_mem"):
                    from modules.auth import IdentityContext

                    metric = "cpu" if act == "kill_top_cpu" else "memory"
                    _, name, pid = self.get_top_process(metric)
                    identity = IdentityContext.service_identity(
                        "proactive", frozenset({"executor.kill"}),
                    )
                    result = await self._gateway.execute(
                        "executor.kill", {"pid": pid},
                        {"identity": identity.to_dict()},
                    )
                    if result.success:
                        return {"status": "executed", "action": f"Killed {name} (PID {pid})"}
                    return {"status": "error", "message": result.error or "Kill failed"}
                raise HTTPException(400, f"Unknown action: {act}")
        raise HTTPException(404, "Suggestion not found")

    def restart_engine(self) -> dict:
        self.stop()
        time.sleep(0.5)
        self.start()
        return {"status": "restarted"}
