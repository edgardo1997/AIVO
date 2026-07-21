"""Windows power plan management via powercfg."""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger(__name__)

SCHEME_GUIDS = {
    "guid_min":  "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "guid_bal":  "381b4222-f694-41f0-9685-ff5bb260df2f",
    "guid_max":  "e9a42b02-d5df-448d-aa00-03f14749eb61",
}

PROFILE_ALIASES = {
    "balanced":         "381b4222-f694-41f0-9685-ff5bb260df2f",
    "balanceado":       "381b4222-f694-41f0-9685-ff5bb260df2f",
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "performance":      "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "alto_rendimiento": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "power_saver":      "e9a42b02-d5df-448d-aa00-03f14749eb61",
    "ahorro":           "e9a42b02-d5df-448d-aa00-03f14749eb61",
    "powersaver":       "e9a42b02-d5df-448d-aa00-03f14749eb61",
    "ultimate":         "e9a42b02-d5df-448d-aa00-03f14749eb61",
}


@dataclass
class PowerPlan:
    guid: str
    name: str
    active: bool = False


@dataclass
class PowerPlanResult:
    success: bool
    plans: List[PowerPlan] = field(default_factory=list)
    active_guid: str = ""
    active_name: str = ""
    error: str = ""


def _run_powercfg(args: List[str]) -> str:
    try:
        result = subprocess.run(
            ["powercfg"] + args,
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log.warning("powercfg %s failed: %s", " ".join(args), result.stderr.strip())
            return ""
        return result.stdout
    except FileNotFoundError:
        log.warning("powercfg not found")
        return ""
    except subprocess.TimeoutExpired:
        log.warning("powercfg %s timed out", " ".join(args))
        return ""
    except Exception as e:
        log.warning("powercfg %s error: %s", " ".join(args), e)
        return ""


def _parse_powercfg_list(stdout: str) -> PowerPlanResult:
    plans: List[PowerPlan] = []
    active_guid = ""

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Active") or line.startswith("---"):
            continue
        m = re.match(
            r"^([0-9a-fA-F\-]{36,})\s*\(\s*([^)]+)\s*\)\s*(\*)?\s*$",
            line,
        )
        if not m:
            m = re.match(
                r"^[^:]*:\s*([0-9a-fA-F\-]{36,})\s*\(\s*([^)]+)\s*\)\s*(\*)?\s*$",
                line,
            )
        if m:
            guid = m.group(1).strip()
            name = m.group(2).strip()
            active = bool(m.group(3) == "*" if m.lastindex >= 3 else False)
            if active:
                active_guid = guid
            plans.append(PowerPlan(guid=guid, name=name, active=active))

    active_name = next((p.name for p in plans if p.active), "")
    return PowerPlanResult(
        success=len(plans) > 0,
        plans=plans,
        active_guid=active_guid,
        active_name=active_name,
    )


def list_plans() -> PowerPlanResult:
    stdout = _run_powercfg(["/list"])
    if not stdout:
        return PowerPlanResult(success=False, error="powercfg not available or returned no output")
    return _parse_powercfg_list(stdout)


def get_active_plan() -> PowerPlanResult:
    return list_plans()


def set_active_plan(guid_or_alias: str) -> PowerPlanResult:
    guid = PROFILE_ALIASES.get(guid_or_alias.lower(), guid_or_alias)

    if not re.match(r"^[\w\-]{36}$", guid):
        available = list_plans()
        if not available.success:
            return PowerPlanResult(success=False, error="No power plans available")
        match = next((p for p in available.plans if p.guid.startswith(guid)), None)
        if not match:
            return PowerPlanResult(success=False, error=f"Power plan '{guid_or_alias}' not found")
        guid = match.guid

    stdout = _run_powercfg(["/setactive", guid])
    if stdout is None:
        return PowerPlanResult(success=False, error="powercfg not available")

    result = list_plans()
    if result.success and result.active_guid == guid:
        return result

    current = list_plans()
    if current.success:
        return current
    return PowerPlanResult(success=False, error=f"Failed to set active plan to {guid}")
