"""System optimizer: detect context and apply optimal mode automatically."""

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from sentinel.core import power_manager, gpu_manager, process_manager, environment_snapshot

log = logging.getLogger(__name__)

# --- Context patterns ---

GAME_PROCESSES = frozenset({
    "steam.exe", "epicgameslauncher.exe", "ubisoftconnect.exe",
    "battlenet.exe", "riotclient.exe", "leagueclient.exe",
    "valorant.exe", "csgo.exe", "dota2.exe", "fortnite.exe",
    "minecraft.exe", "javaw.exe", "eldenring.exe", "cyberpunk2077.exe",
    "rocketleague.exe", "gta5.exe", "r5apex.exe", "overwatch.exe",
    "rainbow6.exe", "cod.exe", "modernwarfare.exe", "warzone.exe",
    "destiny2.exe", "halo.exe", "borderlands3.exe",
})

STREAMING_PROCESSES = frozenset({
    "obs64.exe", "obs32.exe", "streamlabs.exe", "xsplit.exe",
    "twitchstudio.exe", "discord.exe", "slack.exe",
})

IDE_PROCESSES = frozenset({
    "code.exe", "devenv.exe", "idea64.exe", "pycharm64.exe",
    "eclipse.exe", "sublime_text.exe", "notepad++.exe",
    "clion64.exe", "webstorm64.exe", "goland64.exe",
})

BROWSER_PROCESSES = frozenset({
    "chrome.exe", "firefox.exe", "msedge.exe", "brave.exe",
    "opera.exe", "vivaldi.exe",
})


@dataclass
class SystemContext:
    running_games: List[str] = field(default_factory=list)
    running_streaming: List[str] = field(default_factory=list)
    running_ides: List[str] = field(default_factory=list)
    running_browsers: List[str] = field(default_factory=list)
    active_power_plan: str = ""
    cpu_usage_pct: float = 0.0
    memory_usage_pct: float = 0.0
    on_battery: bool = False
    gpu_active: bool = False


@dataclass
class OptimizationResult:
    success: bool
    mode: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    snapshot_id: str = ""


# --- Detection ---

def _detect_context() -> SystemContext:
    ctx = SystemContext()

    procs = process_manager.list_processes(include_system=False)
    if procs.success:
        for p in procs.processes:
            name = p.name.lower()
            if name in GAME_PROCESSES:
                ctx.running_games.append(p.name)
            if name in STREAMING_PROCESSES:
                ctx.running_streaming.append(p.name)
            if name in IDE_PROCESSES:
                ctx.running_ides.append(p.name)
            if name in BROWSER_PROCESSES:
                ctx.running_browsers.append(p.name)

    power = power_manager.get_active_plan()
    if power.success:
        ctx.active_power_plan = power.active_name

    gpu = gpu_manager.list_gpus()
    if gpu.success:
        for g in gpu.gpus:
            if g.gpu_util_pct > 10:
                ctx.gpu_active = True

    try:
        import psutil
        ctx.cpu_usage_pct = psutil.cpu_percent(interval=0.1)
        ctx.memory_usage_pct = psutil.virtual_memory().percent
    except Exception:
        log.warning("Failed to read CPU/memory usage", exc_info=True)

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings",
                            0, winreg.KEY_READ):
            pass
    except Exception:
        log.warning("Failed to read power settings registry", exc_info=True)

    return ctx


# --- Mode selection ---

def _select_mode(ctx: SystemContext) -> str:
    if ctx.running_games:
        return "gaming"
    if ctx.running_streaming:
        return "streaming"
    if ctx.running_ides:
        return "developer"
    if ctx.gpu_active and ctx.cpu_usage_pct > 50:
        return "performance"
    if ctx.cpu_usage_pct > 0 and ctx.cpu_usage_pct < 15 and ctx.memory_usage_pct < 40:
        return "power_saver"
    return "balanced"


# --- Mode application ---

def _apply_gaming() -> List[str]:
    actions = []
    pw = power_manager.set_active_plan("ultimate")
    if pw.success:
        actions.append(f"power_plan={pw.active_name}")
    gp = gpu_manager.set_gpu_profile("gaming")
    if gp.success:
        actions.append("gpu_profile=gaming")
    return actions


def _apply_streaming() -> List[str]:
    actions = []
    pw = power_manager.set_active_plan("balanced")
    if pw.success:
        actions.append(f"power_plan={pw.active_name}")
    gp = gpu_manager.set_gpu_profile("quiet")
    if gp.success:
        actions.append("gpu_profile=quiet")
    return actions


def _apply_developer() -> List[str]:
    actions = []
    pw = power_manager.set_active_plan("balanced")
    if pw.success:
        actions.append(f"power_plan={pw.active_name}")
    gp = gpu_manager.set_gpu_profile("default")
    if gp.success:
        actions.append("gpu_profile=default")
    return actions


def _apply_performance() -> List[str]:
    actions = []
    pw = power_manager.set_active_plan("high_performance")
    if pw.success:
        actions.append(f"power_plan={pw.active_name}")
    gp = gpu_manager.set_gpu_profile("max_performance")
    if gp.success:
        actions.append("gpu_profile=max_performance")
    return actions


def _apply_power_saver() -> List[str]:
    actions = []
    pw = power_manager.set_active_plan("power_saver")
    if pw.success:
        actions.append(f"power_plan={pw.active_name}")
    gp = gpu_manager.set_gpu_profile("power_saver")
    if gp.success:
        actions.append("gpu_profile=power_saver")
    return actions


def _apply_balanced() -> List[str]:
    actions = []
    pw = power_manager.set_active_plan("balanced")
    if pw.success:
        actions.append(f"power_plan={pw.active_name}")
    gp = gpu_manager.set_gpu_profile("default")
    if gp.success:
        actions.append("gpu_profile=default")
    return actions


_APPLY_MAP = {
    "gaming": _apply_gaming,
    "streaming": _apply_streaming,
    "developer": _apply_developer,
    "performance": _apply_performance,
    "power_saver": _apply_power_saver,
    "balanced": _apply_balanced,
}


# --- Public API ---

def optimize(snapshot: bool = True) -> OptimizationResult:
    ctx = _detect_context()
    mode = _select_mode(ctx)
    log.info("System context detected: mode=%s, games=%d, streaming=%d, ides=%d",
             mode, len(ctx.running_games), len(ctx.running_streaming), len(ctx.running_ides))

    snapshot_id = ""
    if snapshot:
        snap_result = environment_snapshot.create_snapshot(f"pre-optimize-{mode}")
        if snap_result:
            snapshot_id = snap_result.meta.id
            log.info("Pre-optimization snapshot: %s", snapshot_id)

    actions: List[str] = []
    errors: List[str] = []

    apply_fn = _APPLY_MAP.get(mode)
    if apply_fn:
        try:
            actions = apply_fn()
        except Exception as e:
            errors.append(str(e))
            log.warning("Optimization apply failed: %s", e)
    else:
        errors.append(f"Unknown mode: {mode}")

    success = len(actions) > 0 or mode == "balanced"

    return OptimizationResult(
        success=success,
        mode=mode,
        context={
            "games": [g for g in ctx.running_games],
            "streaming_apps": [s for s in ctx.running_streaming],
            "ides": [i for i in ctx.running_ides],
            "browsers": [b for b in ctx.running_browsers],
            "active_power_plan": ctx.active_power_plan,
            "cpu_usage": round(ctx.cpu_usage_pct, 1),
            "memory_usage": round(ctx.memory_usage_pct, 1),
            "gpu_active": ctx.gpu_active,
        },
        actions=actions,
        errors=errors,
        snapshot_id=snapshot_id,
    )


def optimize_dry_run() -> OptimizationResult:
    ctx = _detect_context()
    mode = _select_mode(ctx)
    return OptimizationResult(
        success=True,
        mode=mode,
        context={
            "games": ctx.running_games,
            "streaming_apps": ctx.running_streaming,
            "ides": ctx.running_ides,
            "browsers": ctx.running_browsers,
            "active_power_plan": ctx.active_power_plan,
            "cpu_usage": round(ctx.cpu_usage_pct, 1),
            "memory_usage": round(ctx.memory_usage_pct, 1),
            "gpu_active": ctx.gpu_active,
        },
        actions=[f"would apply: {mode}"],
        errors=[],
        snapshot_id="",
    )
