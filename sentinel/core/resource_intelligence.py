from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class SystemSnapshot:
    online: bool = True
    ram_available_gb: float = 16.0
    ram_total_gb: float = 32.0
    battery_percent: Optional[float] = None
    on_battery: bool = False
    gpu_available: bool = False
    gpu_memory_free_mb: int = 0
    cpu_load_pct: float = 0.0
    power_saver_active: bool = False
    budget_remaining_usd: float = 10.0
    has_budget_constraint: bool = False
    snapshot_time: str = ""

    @property
    def ram_available_pct(self) -> float:
        if self.ram_total_gb <= 0:
            return 100.0
        return (self.ram_available_gb / self.ram_total_gb) * 100.0

    @property
    def low_resources(self) -> bool:
        return (
            self.ram_available_pct < 15
            or (self.on_battery and self.battery_percent is not None and self.battery_percent < 20)
            or self.power_saver_active
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "online": self.online,
            "ram_available_gb": self.ram_available_gb,
            "ram_total_gb": self.ram_total_gb,
            "ram_available_pct": self.ram_available_pct,
            "battery_percent": self.battery_percent,
            "on_battery": self.on_battery,
            "gpu_available": self.gpu_available,
            "gpu_memory_free_mb": self.gpu_memory_free_mb,
            "cpu_load_pct": self.cpu_load_pct,
            "power_saver_active": self.power_saver_active,
            "budget_remaining_usd": self.budget_remaining_usd,
            "has_budget_constraint": self.has_budget_constraint,
            "low_resources": self.low_resources,
        }


@dataclass
class ResourceDecision:
    allowed: bool = True
    reason: str = ""
    score_modifier: int = 0
    restrictions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "score_modifier": self.score_modifier,
            "restrictions": list(self.restrictions),
        }


MODEL_HARDWARE_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "70b": {"min_ram_gb": 64, "min_vram_mb": 48000},
    "40b": {"min_ram_gb": 32, "min_vram_mb": 24000},
    "13b": {"min_ram_gb": 16, "min_vram_mb": 8000},
    "7b": {"min_ram_gb": 8, "min_vram_mb": 4000},
    "3b": {"min_ram_gb": 4, "min_vram_mb": 2000},
    "1b": {"min_ram_gb": 2, "min_vram_mb": 1000},
}

CLOUD_PROVIDERS: Set[str] = {
    "openai", "anthropic", "gemini", "deepseek",
    "groq", "cerebras", "mistral", "openrouter",
    "github_models", "nvidia-nemotron",
}


class ResourceIntelligenceLayer:
    def __init__(
        self,
        network_monitor: Any = None,
        cost_tracker: Any = None,
        performance_tracker: Any = None,
    ):
        self._network = network_monitor
        self._cost_tracker = cost_tracker
        self._performance = performance_tracker

    def set_network_monitor(self, monitor: Any) -> None:
        self._network = monitor

    def set_cost_tracker(self, tracker: Any) -> None:
        self._cost_tracker = tracker

    def set_performance_tracker(self, tracker: Any) -> None:
        self._performance = tracker

    def snapshot(self) -> SystemSnapshot:
        try:
            import psutil
            ram = psutil.virtual_memory()
            # Remove blocking interval=0.1 - use interval=0 for non-blocking measurement
            cpu = psutil.cpu_percent(interval=0)
            ram_avail = ram.available / (1024 ** 3)
            ram_total = ram.total / (1024 ** 3)
        except Exception:
            ram_avail = 16.0
            ram_total = 32.0
            cpu = 0.0

        online = self._is_online()
        battery_pct, on_battery = self._get_battery()
        gpu_avail, gpu_free = self._get_gpu()
        power_saver = self._is_power_saver()
        budget = self._get_budget_remaining()
        has_budget = self._has_budget()

        return SystemSnapshot(
            online=online,
            ram_available_gb=round(ram_avail, 1),
            ram_total_gb=round(ram_total, 1),
            battery_percent=battery_pct,
            on_battery=on_battery,
            gpu_available=gpu_avail,
            gpu_memory_free_mb=gpu_free,
            cpu_load_pct=round(cpu, 1),
            power_saver_active=power_saver,
            budget_remaining_usd=budget,
            has_budget_constraint=has_budget,
            snapshot_time=datetime.now(timezone.utc).isoformat(),
        )

    def evaluate(self, model: Any, state: Optional[SystemSnapshot] = None) -> ResourceDecision:
        if state is None:
            state = self.snapshot()
        model_id = getattr(model, "id", str(model))
        provider = getattr(model, "provider", "unknown")
        is_local = getattr(model, "local", False)
        cost = getattr(model, "cost", 0.0)

        restrictions: List[str] = []

        if self._is_cloud_model(provider) and not state.online:
            return ResourceDecision(
                allowed=False,
                reason=f"Model '{model_id}' requires internet (provider={provider}) but system is offline",
                score_modifier=-100,
                restrictions=["offline"],
            )

        if not is_local and not state.online:
            return ResourceDecision(
                allowed=False,
                reason=f"Model '{model_id}' requires internet but system is offline",
                score_modifier=-100,
                restrictions=["offline"],
            )

        hw_req = self._get_hardware_requirement(model_id)
        if hw_req:
            min_ram = hw_req.get("min_ram_gb", 0)
            min_vram = hw_req.get("min_vram_mb", 0)
            if min_ram > 0 and state.ram_available_gb < min_ram:
                return ResourceDecision(
                    allowed=False,
                    reason=f"Insufficient RAM: need {min_ram}GB, have {state.ram_available_gb}GB available",
                    score_modifier=-100,
                    restrictions=["insufficient_ram"],
                )
            if min_vram > 0 and state.gpu_available and state.gpu_memory_free_mb < min_vram:
                return ResourceDecision(
                    allowed=False,
                    reason=f"Insufficient VRAM: need {min_vram}MB, have {state.gpu_memory_free_mb}MB free",
                    score_modifier=-100,
                    restrictions=["insufficient_vram"],
                )

        if state.has_budget_constraint and not is_local:
            estimated = self._estimate_model_cost(provider, model_id)
            model_cost = cost if cost > 0 else estimated
            if model_cost > state.budget_remaining_usd:
                return ResourceDecision(
                    allowed=False,
                    reason=f"Cost ${model_cost:.2f} exceeds remaining budget ${state.budget_remaining_usd:.2f}",
                    score_modifier=-100,
                    restrictions=["budget_exceeded"],
                )

        score_mod = 0
        if is_local and not state.online:
            score_mod += 30
        if is_local:
            score_mod += 10
        if state.on_battery and is_local:
            score_mod += 15
        if state.power_saver_active and is_local:
            score_mod += 10
        if state.on_battery and not is_local:
            score_mod -= 20
        if cost == 0:
            score_mod += 5
        if state.ram_available_pct < 20:
            score_mod -= 25
        if state.cpu_load_pct > 80:
            score_mod -= 15

        is_slow = getattr(model, "speed", "unknown") == "slow"
        if is_slow:
            score_mod -= 10

        reasons = []
        if score_mod > 0:
            reasons.append(f"resource bonus: +{score_mod}")
        elif score_mod < 0:
            reasons.append(f"resource penalty: {score_mod}")

        return ResourceDecision(
            allowed=True,
            reason="; ".join(reasons) if reasons else "compatible",
            score_modifier=score_mod,
            restrictions=restrictions,
        )

    def evaluate_all(
        self, candidates: List[Any], state: Optional[SystemSnapshot] = None
    ) -> List[Tuple[Any, ResourceDecision]]:
        if state is None:
            state = self.snapshot()
        return [(m, self.evaluate(m, state)) for m in candidates]

    def filter_candidates(
        self, candidates: List[Any], state: Optional[SystemSnapshot] = None
    ) -> List[Tuple[Any, ResourceDecision]]:
        evaluated = self.evaluate_all(candidates, state)
        return [(m, d) for m, d in evaluated if d.allowed]

    def find_fallback(
        self, candidates: List[Any], rejected_ids: Set[str], state: Optional[SystemSnapshot] = None
    ) -> Optional[Tuple[Any, ResourceDecision]]:
        if state is None:
            state = self.snapshot()
        for m in candidates:
            if getattr(m, "id", "") in rejected_ids:
                continue
            decision = self.evaluate(m, state)
            if decision.allowed:
                return m, decision
        return None

    def _is_online(self) -> bool:
        if self._network is not None:
            try:
                if hasattr(self._network, "is_online"):
                    return self._network.is_online
            except Exception:
                logger.warning("Network monitor failed; treating connectivity as unknown", exc_info=True)
        return True

    def _get_battery(self) -> tuple:
        try:
            import psutil
            if not psutil.sensors_battery:
                return None, False
            batt = psutil.sensors_battery()
            if batt is None:
                return None, False
            return round(batt.percent, 1), batt.power_plugged is False
        except Exception:
            return None, False

    def _get_gpu(self) -> tuple:
        try:
            from sentinel.core.gpu_manager import list_gpus
            result = list_gpus()
            if result.success and result.gpus:
                gpu = result.gpus[0]
                return True, gpu.memory_free_mb
        except Exception:
            logger.warning("Failed to read GPU resources", exc_info=True)
        return False, 0

    def _is_power_saver(self) -> bool:
        try:
            from sentinel.core.power_manager import get_active_plan
            result = get_active_plan()
            if result.success and result.active_name:
                name = result.active_name.lower()
                return "powersaver" in name or "power saver" in name or "ahorro" in name
        except Exception:
            logger.warning("Failed to read active power plan", exc_info=True)
        return False

    def _get_budget_remaining(self) -> float:
        if self._cost_tracker is not None and hasattr(self._cost_tracker, "check_budgets"):
            try:
                alerts = self._cost_tracker.check_budgets()
                if alerts:
                    worst = max(alerts, key=lambda a: a.current_cost / max(a.max_cost, 0.01))
                    return max(0, worst.max_cost - worst.current_cost)
            except Exception:
                logger.warning("Failed to read remaining model budget", exc_info=True)
        return 10.0

    def _has_budget(self) -> bool:
        if self._cost_tracker is not None and hasattr(self._cost_tracker, "get_budgets"):
            try:
                return len(self._cost_tracker.get_budgets()) > 0
            except Exception:
                logger.warning("Failed to read model budget constraints", exc_info=True)
        return False

    def _estimate_model_cost(self, provider: str, model_id: str) -> float:
        if self._cost_tracker is not None and hasattr(self._cost_tracker, "estimate_cost"):
            try:
                return self._cost_tracker.estimate_cost(provider, model_id, 2000, 500)
            except Exception:
                logger.warning("Failed to estimate model cost for '%s'", model_id, exc_info=True)
        return 0.01

    def _get_hardware_requirement(self, model_id: str) -> Optional[Dict[str, Any]]:
        model_lower = model_id.lower()
        for size_tag, req in MODEL_HARDWARE_REQUIREMENTS.items():
            if size_tag in model_lower:
                return req
        for tag in ["70b", "40b", "13b", "7b", "3b", "1b"]:
            if tag in model_lower:
                return MODEL_HARDWARE_REQUIREMENTS.get(tag)
        return None

    def _is_cloud_model(self, provider: str) -> bool:
        return provider in CLOUD_PROVIDERS
