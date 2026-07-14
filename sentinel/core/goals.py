from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import threading

from .capability_registry import RiskLevel


@dataclass
class GoalDefinition:
    id: str
    name: str
    description: str
    related_intents: List[str]
    possible_capabilities: List[str]
    priority: int = 0
    base_risk: RiskLevel = RiskLevel.LOW
    keywords: List[str] = field(default_factory=list)
    context_rules: Dict[str, float] = field(default_factory=dict)
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["base_risk"] = self.base_risk.value
        return d

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "GoalDefinition":
        data = dict(data)
        data["base_risk"] = RiskLevel(data["base_risk"])
        return GoalDefinition(**data)


@dataclass
class GoalAuditEntry:
    timestamp: str
    operation: str
    goal_id: str
    source: str
    details: Dict[str, Any]


@dataclass
class GoalScorerConfig:
    min_confidence: float = 0.3
    confidence_weight: float = 0.6
    priority_weight: float = 0.2
    context_weight: float = 0.2
    max_audit_entries: int = 1000


@dataclass
class Goal:
    definition: GoalDefinition
    context: Optional[Dict[str, Any]] = None

    @property
    def id(self) -> str:
        return self.definition.id

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def base_risk(self) -> RiskLevel:
        return self.definition.base_risk

    @property
    def priority(self) -> int:
        return self.definition.priority

    @property
    def related_intents(self) -> List[str]:
        return self.definition.related_intents

    @property
    def possible_capabilities(self) -> List[str]:
        return self.definition.possible_capabilities


_ALLOWED_UPDATE_FIELDS = frozenset({
    "name", "description", "related_intents", "possible_capabilities",
    "priority", "base_risk", "keywords", "enabled", "context_rules",
})


class GoalRegistry:
    def __init__(self, max_audit_entries: int = 1000) -> None:
        self._definitions: Dict[str, GoalDefinition] = {}
        self._intent_index: Dict[str, List[str]] = {}
        self._audit_log: List[GoalAuditEntry] = []
        self._max_audit_entries = max_audit_entries
        self._lock = threading.RLock()
        self._test_skip_cap_validation: bool = False

    def set_max_audit_entries(self, n: int) -> None:
        with self._lock:
            self._max_audit_entries = n
            while len(self._audit_log) > self._max_audit_entries:
                self._audit_log.pop(0)

    def _audit(self, operation: str, goal_id: str, source: str, details: Dict[str, Any]) -> None:
        entry = GoalAuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation=operation,
            goal_id=goal_id,
            source=source,
            details=details,
        )
        self._audit_log.append(entry)
        while len(self._audit_log) > self._max_audit_entries:
            self._audit_log.pop(0)

    def register(self, definition: GoalDefinition, source: str = "system") -> None:
        with self._lock:
            if definition.id in self._definitions:
                raise ValueError(f"Goal '{definition.id}' already registered")
            self._definitions[definition.id] = definition
            for intent_target in definition.related_intents:
                self._intent_index.setdefault(intent_target, []).append(definition.id)
            self._audit("REGISTER", definition.id, source, {
                "priority": definition.priority,
                "intents": list(definition.related_intents),
                "caps": list(definition.possible_capabilities),
            })

    def unregister(self, goal_id: str, source: str = "system") -> None:
        with self._lock:
            if goal_id not in self._definitions:
                raise KeyError(f"Goal '{goal_id}' not found")
            old = self._definitions.pop(goal_id)
            for intent_target in old.related_intents:
                idx = self._intent_index.get(intent_target, [])
                if goal_id in idx:
                    idx.remove(goal_id)
                    if not idx:
                        del self._intent_index[intent_target]
            self._audit("DELETE", goal_id, source, {"goal_id": goal_id})

    def update(self, goal_id: str, changes: Dict[str, Any], source: str = "system") -> GoalDefinition:
        with self._lock:
            if goal_id not in self._definitions:
                raise KeyError(f"Goal '{goal_id}' not found")
            old = self._definitions[goal_id]
            old_intents = list(old.related_intents)
            for key, value in changes.items():
                if key not in _ALLOWED_UPDATE_FIELDS:
                    raise ValueError(f"Field '{key}' is not allowed for update")
                if key == "related_intents":
                    for intent_target in old_intents:
                        idx = self._intent_index.get(intent_target, [])
                        if goal_id in idx:
                            idx.remove(goal_id)
                            if not idx:
                                del self._intent_index[intent_target]
                    for intent_target in value:
                        self._intent_index.setdefault(intent_target, []).append(goal_id)
                setattr(old, key, value)
            old.updated_at = datetime.now(timezone.utc).isoformat()
            self._audit("UPDATE", goal_id, source, {"changed_fields": list(changes.keys())})
            return old

    def get(self, goal_id: str) -> Optional[GoalDefinition]:
        with self._lock:
            return self._definitions.get(goal_id)

    def find_by_intent(self, intent_target: str) -> List[GoalDefinition]:
        with self._lock:
            goal_ids = self._intent_index.get(intent_target, [])
            return [self._definitions[gid] for gid in goal_ids if gid in self._definitions]

    _STOPWORDS = {"system", "executor", "scheduler", "manage"}

    @staticmethod
    def _token_similarity(a: str, b: str) -> float:
        a_tokens = set(a.replace(".", " ").replace("_", " ").split())
        b_tokens = set(b.replace(".", " ").replace("_", " ").split())
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = a_tokens & b_tokens
        meaningful = intersection - GoalRegistry._STOPWORDS
        if not meaningful:
            return 0.0
        return len(intersection) / len(a_tokens | b_tokens)

    def search_by_intent(self, intent_target: str, threshold: float = 0.3) -> List[GoalDefinition]:
        with self._lock:
            seen: set = set()
            results: List[GoalDefinition] = []
            for goal in self._definitions.values():
                for ref in goal.related_intents:
                    if self._token_similarity(intent_target, ref) >= threshold:
                        if goal.id not in seen:
                            results.append(goal)
                            seen.add(goal.id)
                        break
            return results

    def list_all(self) -> List[GoalDefinition]:
        with self._lock:
            return list(self._definitions.values())

    def clear(self) -> None:
        with self._lock:
            self._definitions.clear()
            self._intent_index.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._definitions)

    def get_audit_log(self) -> List[GoalAuditEntry]:
        with self._lock:
            return list(self._audit_log)

    def find_candidates(self, intent_target: str) -> "List[GoalMatchResult]":
        with self._lock:
            results: List[GoalMatchResult] = []
            seen: set = set()

            # 1. Exact match on related_intents
            for gid in self._intent_index.get(intent_target, []):
                if gid in self._definitions:
                    results.append(GoalMatchResult(
                        goal=self._definitions[gid],
                        confidence=1.0,
                        match_type="exact",
                        matched_by=intent_target,
                    ))
                    seen.add(gid)

            # 2. Fuzzy match on related_intents
            for goal in self._definitions.values():
                if goal.id in seen:
                    continue
                for ref in goal.related_intents:
                    sim = self._token_similarity(intent_target, ref)
                    if sim >= 0.3:
                        conf = round(min(0.5 + sim * 0.4, 0.95), 2)
                        results.append(GoalMatchResult(
                            goal=goal, confidence=conf,
                            match_type="fuzzy_intent", matched_by=ref,
                        ))
                        seen.add(goal.id)
                        break

            # 3. Match against possible_capabilities (fuzzy only, skip exact self-match)
            for goal in self._definitions.values():
                if goal.id in seen:
                    continue
                for cap in goal.possible_capabilities:
                    if intent_target == cap:
                        continue
                    sim = self._token_similarity(intent_target, cap)
                    if sim >= 0.3:
                        conf = round(min(0.4 + sim * 0.4, 0.85), 2)
                        results.append(GoalMatchResult(
                            goal=goal, confidence=conf,
                            match_type="capability", matched_by=cap,
                        ))
                        seen.add(goal.id)
                        break

            # 4. Keyword match on name / description / keywords field
            target_tokens = set(
                intent_target.replace(".", " ").replace("_", " ").lower().split()
            ) - self._STOPWORDS
            for goal in self._definitions.values():
                if goal.id in seen:
                    continue
                kw_text = " ".join(goal.keywords) if hasattr(goal, "keywords") else ""
                nd = f"{goal.name} {goal.description} {kw_text}"
                nd_tokens = set(nd.replace(".", " ").replace("_", " ").lower().split()) - self._STOPWORDS
                overlap = target_tokens & nd_tokens
                if overlap:
                    results.append(GoalMatchResult(
                        goal=goal, confidence=0.4,
                        match_type="keyword",
                        matched_by=", ".join(sorted(overlap)),
                    ))
                    seen.add(goal.id)

            return results


@dataclass
class GoalMatchResult:
    goal: GoalDefinition
    confidence: float
    match_type: str
    matched_by: str


@dataclass
class ScoredGoal:
    result: GoalMatchResult
    score: float
    reasons: List[str]


class GoalScorer:
    def __init__(self, context: Optional[Dict[str, Any]] = None,
                 config: Optional[GoalScorerConfig] = None) -> None:
        self._context = context or {}
        self._config = config or GoalScorerConfig()

    def rank(self, candidates: List[GoalMatchResult]) -> List[ScoredGoal]:
        min_conf = self._config.min_confidence
        scored = [self._score(c) for c in candidates if c.confidence >= min_conf]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def _score(self, candidate: GoalMatchResult) -> ScoredGoal:
        cw = self._config.confidence_weight
        pw = self._config.priority_weight
        ctw = self._config.context_weight
        base = candidate.confidence * cw
        priority_bonus = (candidate.goal.priority / 10.0) * pw
        context_bonus = self._context_bonus(candidate.goal) * ctw
        score = round(base + priority_bonus + context_bonus, 4)
        reasons = self._compute_reasons(candidate)
        return ScoredGoal(result=candidate, score=score, reasons=reasons)

    def get_config(self) -> GoalScorerConfig:
        return self._config

    def _context_bonus(self, goal: GoalDefinition) -> float:
        rules = goal.context_rules
        if not rules:
            return 0.0
        cpu = self._context.get("cpu_percent", 50)
        mem = self._context.get("memory_percent", 50)
        disk = self._context.get("disk_percent", 50)
        bonus = 0.0
        if cpu > 80:
            bonus += rules.get("cpu_high", 0.0)
        if mem > 80:
            bonus += rules.get("mem_high", 0.0)
        if disk > 85:
            bonus += rules.get("disk_high", 0.0)
        return min(bonus, 1.0)

    def _compute_reasons(self, candidate: GoalMatchResult) -> List[str]:
        reasons = [f"{candidate.match_type}_via_{candidate.matched_by}"]
        cpu = self._context.get("cpu_percent")
        mem = self._context.get("memory_percent")
        disk = self._context.get("disk_percent")
        if cpu is not None and cpu > 80:
            reasons.append("high_cpu_context")
        if mem is not None and mem > 80:
            reasons.append("high_memory_context")
        if disk is not None and disk > 85:
            reasons.append("high_disk_context")
        return reasons


def create_default_goal_registry(max_audit_entries: int = 1000) -> GoalRegistry:
    registry = GoalRegistry(max_audit_entries=max_audit_entries)
    registry.register(GoalDefinition(
        id="system_health_diagnosis",
        name="System Health Diagnosis",
        description="Analyze overall system health and performance",
        related_intents=["system.health"],
        possible_capabilities=[
            "system.cpu",
            "system.info",
            "system.processes",
        ],
        priority=8,
        base_risk=RiskLevel.LOW,
        context_rules={"cpu_high": 0.3, "mem_high": 0.3, "disk_high": 0.3},
    ))
    registry.register(GoalDefinition(
        id="disk_space_cleanup",
        name="Disk Space Cleanup",
        description="Identify and free disk space by analyzing storage usage",
        related_intents=["system.disk"],
        possible_capabilities=[
            "system.info",
        ],
        priority=5,
        base_risk=RiskLevel.LOW,
        context_rules={"disk_high": 1.0},
    ))
    registry.register(GoalDefinition(
        id="network_diagnosis",
        name="Network Diagnosis",
        description="Troubleshoot network connectivity and performance issues",
        related_intents=["system.network"],
        possible_capabilities=[
            "system.info",
            "system.processes",
        ],
        priority=6,
        base_risk=RiskLevel.LOW,
        context_rules={},
    ))
    registry.register(GoalDefinition(
        id="performance_tuning",
        name="Performance Tuning",
        description="Optimize system performance by analyzing resource usage",
        related_intents=["system.cpu", "system.processes", "system.memory"],
        possible_capabilities=[
            "system.cpu",
            "system.info",
            "system.processes",
        ],
        priority=7,
        base_risk=RiskLevel.LOW,
        context_rules={"cpu_high": 0.5, "mem_high": 0.5},
    ))
    return registry
