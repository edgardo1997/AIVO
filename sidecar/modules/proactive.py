import json
import os
import time
import threading
import psutil
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
import logging
from .permissions import check_permission
from .audit import log_action
from .plugins import run_hook, ACTIVE_PLUGINS

log = logging.getLogger("aivo.proactive")

router = APIRouter()

SUGGESTIONS: list = []
METRICS_HISTORY: list = []
MAX_HISTORY = 60
SCAN_INTERVAL = 30
AI_SCAN_INTERVAL = 120
last_scan = 0
last_ai_scan = 0
engine_active = False

THRESHOLDS = {
    "cpu_percent": {"warning": 70, "critical": 90},
    "memory_percent": {"warning": 75, "critical": 90},
    "disk_percent": {"warning": 85, "critical": 95},
    "swap_percent": {"warning": 50, "critical": 80},
    "process_count_high": 150,
    "uptime_hours_warning": 72,
}

SUGGESTION_TEMPLATES = {
    "high_cpu": {
        "title": "High CPU Usage",
        "icon": "🔥",
        "priority": "warning",
        "message": "CPU at {value}% — {process} using the most.",
        "actions": [
            {"label": "Kill top process", "action": "kill_top_cpu"},
            {"label": "Open Task Manager", "action": "launch:taskmgr"},
        ],
    },
    "high_memory": {
        "title": "High Memory Usage",
        "icon": "💾",
        "priority": "warning",
        "message": "RAM at {value}% ({used}/{total}). Consider closing memory-heavy apps.",
        "actions": [
            {"label": "Show top RAM processes", "action": "show_top_ram"},
            {"label": "Open Task Manager", "action": "launch:taskmgr"},
        ],
    },
    "critical_memory": {
        "title": "Critical Memory",
        "icon": "🚨",
        "priority": "critical",
        "message": "RAM at {value}% — system may become unstable.",
        "actions": [
            {"label": "Kill top memory process", "action": "kill_top_ram"},
            {"label": "Emergency cleanup", "action": "suggest:cleanup"},
        ],
    },
    "high_disk": {
        "title": "Disk Space Low",
        "icon": "💿",
        "priority": "warning",
        "message": "{mount} is at {value}% ({free} free).",
        "actions": [
            {"label": "Run Disk Cleanup", "action": "launch:cleanmgr"},
            {"label": "Show large folders", "action": "suggest:large_files"},
        ],
    },
    "long_uptime": {
        "title": "System Running Long",
        "icon": "⏰",
        "priority": "info",
        "message": "Uptime: {value} hours. A restart may improve performance.",
        "actions": [
            {"label": "Schedule restart", "action": "suggest:restart"},
        ],
    },
    "high_temp": {
        "title": "High Temperature",
        "icon": "🌡️",
        "priority": "critical",
        "message": "CPU at {value}°C. Check cooling.",
        "actions": [
            {"label": "Show temp details", "action": "suggest:temp"},
        ],
    },
    "many_processes": {
        "title": "Many Running Processes",
        "icon": "⚙️",
        "priority": "info",
        "message": "{value} processes running. Some may be unnecessary.",
        "actions": [
            {"label": "Show all processes", "action": "navigate:monitor"},
        ],
    },
    "high_swap": {
        "title": "High Swap Usage",
        "icon": "🔄",
        "priority": "warning",
        "message": "Swap at {value}%. System is using disk as RAM.",
        "actions": [
            {"label": "Show memory details", "action": "navigate:monitor"},
        ],
    },
    "ai_insight": {
        "title": "AI Insight",
        "icon": "🧠",
        "priority": "info",
        "message": "{message}",
        "actions": [],
    },
}

def format_bytes(b):
    if b >= 1e12: return f"{b/1e12:.1f} TB"
    if b >= 1e9: return f"{b/1e9:.1f} GB"
    if b >= 1e6: return f"{b/1e6:.1f} MB"
    return f"{b/1e3:.0f} KB"

def get_top_process(metric="cpu"):
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            val = p.info.get(f"{metric}_percent", 0) or 0
            procs.append((val, p.info["name"], p.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            log.debug("Error reading process info: %s", e)
    procs.sort(reverse=True)
    if procs:
        return procs[0]
    return (0, "unknown", 0)

def check_thresholds():
    global SUGGESTIONS
    now = time.time()
    new_suggestions = []

    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    boot = psutil.boot_time()
    uptime_hours = (now - boot) / 3600
    procs = len(list(psutil.process_iter()))
    disk_parts = []
    for p in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(p.mountpoint)
            disk_parts.append((p.mountpoint, u.percent, u.free))
        except PermissionError:
            log.debug("Permission denied for mount: %s", p.mountpoint)
        except OSError as e:
            log.warning("Error reading disk: %s", e)

    # CPU threshold
    if cpu > THRESHOLDS["cpu_percent"]["critical"]:
        val, name, pid = get_top_process("cpu")
        s = dict(SUGGESTION_TEMPLATES["high_cpu"])
        s["message"] = s["message"].format(value=cpu, process=f"{name} ({pid})")
        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
        s["id"] = f"cpu_{int(now)}"
        s["context"] = {"cpu": cpu, "top_process": name, "pid": pid}
        new_suggestions.append(s)
    elif cpu > THRESHOLDS["cpu_percent"]["warning"]:
        val, name, pid = get_top_process("cpu")
        s = dict(SUGGESTION_TEMPLATES["high_cpu"])
        s["message"] = s["message"].format(value=cpu, process=f"{name}")
        s["priority"] = "info"
        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
        s["id"] = f"cpu_{int(now)}"
        s["context"] = {"cpu": cpu}
        new_suggestions.append(s)

    # Memory threshold
    if mem.percent > THRESHOLDS["memory_percent"]["critical"]:
        s = dict(SUGGESTION_TEMPLATES["critical_memory"])
        s["message"] = s["message"].format(value=mem.percent)
        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
        s["id"] = f"mem_{int(now)}"
        s["context"] = {"memory_percent": mem.percent, "used": mem.used, "total": mem.total}
        new_suggestions.append(s)
    elif mem.percent > THRESHOLDS["memory_percent"]["warning"]:
        s = dict(SUGGESTION_TEMPLATES["high_memory"])
        s["message"] = s["message"].format(value=mem.percent, used=format_bytes(mem.used), total=format_bytes(mem.total))
        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
        s["id"] = f"mem_{int(now)}"
        s["context"] = {"memory_percent": mem.percent}
        new_suggestions.append(s)

    # Disk threshold
    for mount, percent, free in disk_parts:
        if percent > THRESHOLDS["disk_percent"]["critical"]:
            s = dict(SUGGESTION_TEMPLATES["high_disk"])
            s["priority"] = "critical"
            s["message"] = s["message"].format(mount=mount, value=percent, free=format_bytes(free))
            s["timestamp"] = datetime.utcnow().isoformat() + "Z"
            s["id"] = f"disk_{mount.replace(':','')}_{int(now)}"
            s["context"] = {"disk_percent": percent, "mount": mount}
            new_suggestions.append(s)
        elif percent > THRESHOLDS["disk_percent"]["warning"]:
            s = dict(SUGGESTION_TEMPLATES["high_disk"])
            s["message"] = s["message"].format(mount=mount, value=percent, free=format_bytes(free))
            s["timestamp"] = datetime.utcnow().isoformat() + "Z"
            s["id"] = f"disk_{int(now)}"
            s["context"] = {"disk_percent": percent}
            new_suggestions.append(s)

    # Swap threshold
    if swap.percent > THRESHOLDS["swap_percent"]["critical"]:
        s = dict(SUGGESTION_TEMPLATES["high_swap"])
        s["priority"] = "critical"
        s["message"] = s["message"].format(value=swap.percent)
        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
        s["id"] = f"swap_{int(now)}"
        s["context"] = {"swap_percent": swap.percent}
        new_suggestions.append(s)

    # Uptime threshold
    if uptime_hours > THRESHOLDS["uptime_hours_warning"]:
        s = dict(SUGGESTION_TEMPLATES["long_uptime"])
        s["message"] = s["message"].format(value=int(uptime_hours))
        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
        s["id"] = f"uptime_{int(now)}"
        s["context"] = {"uptime_hours": uptime_hours}
        new_suggestions.append(s)

    # Many processes
    if procs > THRESHOLDS["process_count_high"]:
        s = dict(SUGGESTION_TEMPLATES["many_processes"])
        s["message"] = s["message"].format(value=procs)
        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
        s["id"] = f"procs_{int(now)}"
        s["context"] = {"process_count": procs}
        new_suggestions.append(s)

    # Merge: keep existing non-expired, add new
    now_dt = datetime.utcnow()
    SUGGESTIONS = [s for s in SUGGESTIONS if s.get("id") and not s.get("dismissed", False) and
                   (now_dt - datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))).total_seconds() < 300]
    existing_ids = {s["id"] for s in SUGGESTIONS}
    for s in new_suggestions:
        if s["id"] not in existing_ids:
            SUGGESTIONS.append(s)

def store_metrics_snapshot():
    snapshot = {
        "timestamp": time.time(),
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_used": psutil.virtual_memory().used,
        "disk_percent": max([p.percent for p in psutil.disk_partitions()], default=0) if True else 0,
        "process_count": len(list(psutil.process_iter())),
    }
    METRICS_HISTORY.append(snapshot)
    if len(METRICS_HISTORY) > MAX_HISTORY:
        METRICS_HISTORY.pop(0)

def get_trend():
    if len(METRICS_HISTORY) < 10:
        return {}
    recent = METRICS_HISTORY[-10:]
    old = METRICS_HISTORY[:10]
    trends = {}
    for key in ["cpu_percent", "memory_percent", "disk_percent", "process_count"]:
        avg_recent = sum(s[key] for s in recent) / len(recent)
        avg_old = sum(s[key] for s in old) / len(old)
        diff = avg_recent - avg_old
        if diff > 5:
            trends[key] = {"direction": "up", "change": round(diff, 1)}
        elif diff < -5:
            trends[key] = {"direction": "down", "change": round(abs(diff), 1)}
        else:
            trends[key] = {"direction": "stable", "change": round(diff, 1)}
    return trends

def run_engine():
    global engine_active, last_scan, last_ai_scan
    engine_active = True
    while engine_active:
        try:
            time.sleep(SCAN_INTERVAL)
            check_thresholds()
            store_metrics_snapshot()

            # Notify plugin hooks
            if ACTIVE_PLUGINS:
                cpu = psutil.cpu_percent(interval=0.2)
                mem = psutil.virtual_memory()
                ctx = {
                    "cpu_percent": cpu,
                    "memory_percent": mem.percent,
                    "memory_used": mem.used,
                    "memory_total": mem.total,
                    "disk_percent": max((p.percent for p in psutil.disk_partitions()), default=0),
                    "process_count": len(list(psutil.process_iter())),
                    "now": time.time(),
                }
                run_hook("on_metrics", ctx)
                run_hook("on_schedule", ctx)

            # AI analysis every N intervals
            if time.time() - last_ai_scan > AI_SCAN_INTERVAL:
                last_ai_scan = time.time()
                try:
                    from .ai_provider import load_config, get_client, SYSTEM_PROMPT
                    cfg = load_config()
                    if cfg.api_key or cfg.provider == "ollama":
                        client = get_client(cfg)
                        cpu = psutil.cpu_percent(interval=0.3)
                        mem = psutil.virtual_memory()
                        metrics_summary = (
                            f"CPU: {cpu}%, RAM: {mem.percent}% ({mem.used/1e9:.1f}/{mem.total/1e9:.1f} GB), "
                            f"Processes: {len(list(psutil.process_iter()))}"
                        )
                        response = client.chat.completions.create(
                            model=cfg.model,
                            messages=[
                                {"role": "system", "content": "You are AIVO's proactive analysis engine. Given system metrics, provide ONE brief insight or suggestion (max 2 sentences). Be specific and actionable. Prefix with either 🔧 OPTIMIZATION: or ℹ️ INFO: or ⚠️ ALERT:"},
                                {"role": "user", "content": f"Current system state: {metrics_summary}. Uptime: {(time.time() - psutil.boot_time())/3600:.0f} hours."},
                            ],
                            temperature=0.5,
                            max_tokens=200,
                        )
                        insight = response.choices[0].message.content.strip()
                        s = dict(SUGGESTION_TEMPLATES["ai_insight"])
                        s["message"] = insight
                        s["timestamp"] = datetime.utcnow().isoformat() + "Z"
                        s["id"] = f"ai_{int(time.time())}"
                        s["priority"] = "info" if insight.startswith("ℹ️") else "warning" if insight.startswith("⚠️") else "info"
                        s["context"] = {}
                        SUGGESTIONS.append(s)
                except Exception as e:
                    log.warning("AI analysis error: %s", e)

        except Exception as e:
            log.warning("Proactive engine error: %s", e)

@router.on_event("startup")
def start_engine():
    thread = threading.Thread(target=run_engine, daemon=True)
    thread.start()

@router.get("/suggestions")
def get_suggestions():
    return {
        "suggestions": SUGGESTIONS[-20:],
        "trends": get_trend(),
        "metrics_count": len(METRICS_HISTORY),
        "engine_active": engine_active,
    }

@router.post("/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: str):
    for s in SUGGESTIONS:
        if s.get("id") == suggestion_id:
            s["dismissed"] = True
            return {"status": "dismissed"}
    return {"status": "not_found"}

@router.post("/suggestions/{suggestion_id}/execute")
def execute_suggestion(suggestion_id: str):
    for s in SUGGESTIONS:
        if s.get("id") == suggestion_id and not s.get("dismissed", False):
            actions = s.get("actions", [])
            if not actions:
                return {"status": "no_actions"}
            first = actions[0]
            action = first["action"]
            if action.startswith("launch:"):
                app = action.split(":", 1)[1]
                import subprocess, shutil
                subprocess.Popen([shutil.which(app) or app], shell=True)
                log_action("suggestion_executed", f"Launched {app}", "success")
                return {"status": "executed", "action": action}
            elif action == "kill_top_cpu":
                import psutil
                procs = [(p.info.get("cpu_percent",0) or 0, p.info["pid"]) for p in psutil.process_iter(["pid","cpu_percent"])]
                procs.sort(reverse=True)
                if procs:
                    psutil.Process(procs[0][1]).terminate()
                    log_action("suggestion_executed", f"Killed top CPU process PID {procs[0][1]}", "success")
                return {"status": "executed", "action": action}
            elif action == "kill_top_ram":
                import psutil
                procs = [(p.info.get("memory_percent",0) or 0, p.info["pid"]) for p in psutil.process_iter(["pid","memory_percent"])]
                procs.sort(reverse=True)
                if procs:
                    psutil.Process(procs[0][1]).terminate()
                return {"status": "executed", "action": action}
            return {"status": "unhandled_action", "action": action}
    return {"status": "not_found"}

@router.get("/metrics-history")
def get_metrics_history():
    return {"history": METRICS_HISTORY[-30:]}

@router.post("/engine/restart")
def restart_engine():
    global engine_active
    engine_active = False
    time.sleep(1)
    thread = threading.Thread(target=run_engine, daemon=True)
    thread.start()
    return {"status": "restarted"}
