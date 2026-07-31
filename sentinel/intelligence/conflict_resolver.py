from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import logging
import re

from sentinel.intelligence.evaluation_engine import EvaluatedResponse

logger = logging.getLogger(__name__)


class ConflictLevel(Enum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"


@dataclass
class Conflict:
    topic: str = ""
    models: List[str] = field(default_factory=list)
    positions: List[str] = field(default_factory=list)
    level: ConflictLevel = ConflictLevel.MODERATE
    resolution: str = ""
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "models": list(self.models),
            "positions": list(self.positions),
            "level": self.level.value,
            "resolution": self.resolution,
            "resolved": self.resolved,
        }


@dataclass
class ConflictReport:
    conflicts: List[Conflict] = field(default_factory=list)
    total_conflicts: int = 0
    resolved_count: int = 0
    unresolved_count: int = 0
    third_opinion_requested: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflicts": [c.to_dict() for c in self.conflicts],
            "total_conflicts": self.total_conflicts,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "third_opinion_requested": self.third_opinion_requested,
        }


KEY_CLAIM_PATTERNS = [
    r"(?i)(?:the|this|that)\s+(\w+(?:\s+\w+){0,3})\s+(?:is|are|was|were)\s+(.+?)(?:\.|$)",
    r"(?i)(\w+(?:\s+\w+){0,3})\s+(?:causes?|leads? to|results? in|triggers?)\s+(.+?)(?:\.|$)",
    r"(?i)(?:because|since|as)\s+(.+?)(?:,|\.|$)",
    r"(?i)(\w+(?:\s+\w+){0,3})\s+(?:should|must|needs? to|ought to)\s+(.+?)(?:\.|$)",
]


def extract_claims(text: str) -> List[Dict[str, str]]:
    claims = []
    for pattern in KEY_CLAIM_PATTERNS:
        for match in re.finditer(pattern, text):
            groups = match.groups()
            if len(groups) >= 2:
                claims.append({"subject": groups[0].strip(), "statement": groups[1].strip()})
            else:
                claims.append({"subject": "general", "statement": groups[0].strip()})
    return claims


def find_conflicts(evaluated_list: List[EvaluatedResponse]) -> List[Conflict]:
    if len(evaluated_list) < 2:
        return []
    all_claims: Dict[str, List[Dict[str, Any]]] = {}
    for ev in evaluated_list:
        claims = extract_claims(ev.response.response_text)
        for claim in claims:
            key = f"{claim['subject']}:{claim['statement'][:60]}"
            if key not in all_claims:
                all_claims[key] = []
            all_claims[key].append({"model_id": ev.response.model_id, "statement": claim['statement'], "subject": claim['subject']})

    conflicts = []
    subjects_seen: Set[str] = set()
    for ev in evaluated_list:
        claims = extract_claims(ev.response.response_text)
        for claim in claims:
            subj = claim['subject'].lower()
            if subj in subjects_seen:
                continue
            subjects_seen.add(subj)
            positions = {}
            for other_ev in evaluated_list:
                other_claims = extract_claims(other_ev.response.response_text)
                matching = [c for c in other_claims if c['subject'].lower() == subj]
                if matching:
                    positions[other_ev.response.model_id] = matching[0]['statement']
            if len(positions) >= 2:
                unique_positions = set(p.lower()[:80] for p in positions.values())
                if len(unique_positions) > 1:
                    conflict_level = ConflictLevel.MINOR if len(unique_positions) <= 2 else ConflictLevel.MODERATE
                    if len(unique_positions) >= 3:
                        conflict_level = ConflictLevel.MAJOR
                    conflicts.append(Conflict(
                        topic=subj,
                        models=list(positions.keys()),
                        positions=list(positions.values()),
                        level=conflict_level,
                    ))
    return conflicts


class ConflictResolver:
    def __init__(self, third_opinion_fn: Optional[Callable[[str], str]] = None):
        self._third_opinion_fn = third_opinion_fn

    def resolve(self, evaluated_list: List[EvaluatedResponse]) -> ConflictReport:
        conflicts = find_conflicts(evaluated_list)
        report = ConflictReport(conflicts=conflicts, total_conflicts=len(conflicts))
        for conflict in conflicts:
            if conflict.level == ConflictLevel.MINOR:
                self._resolve_minor(conflict, evaluated_list)
            elif conflict.level == ConflictLevel.MODERATE:
                self._resolve_moderate(conflict, evaluated_list)
            elif conflict.level == ConflictLevel.MAJOR:
                self._resolve_major(conflict, evaluated_list)
        report.resolved_count = sum(1 for c in conflicts if c.resolved)
        report.unresolved_count = sum(1 for c in conflicts if not c.resolved)
        return report

    def _resolve_minor(self, conflict: Conflict, evaluated_list: List[EvaluatedResponse]) -> None:
        best_idx = self._find_best_index(conflict.models, evaluated_list)
        if best_idx is not None:
            conflict.resolution = f"Adopted position from {evaluated_list[best_idx].response.model_id} (highest confidence)"
        else:
            conflict.resolution = conflict.positions[0]
        conflict.resolved = True

    def _resolve_moderate(self, conflict: Conflict, evaluated_list: List[EvaluatedResponse]) -> None:
        best_idx = self._find_best_index(conflict.models, evaluated_list)
        if best_idx is not None:
            conflict.resolution = f"Adopted position from {evaluated_list[best_idx].response.model_id} (highest adjusted score)"
        else:
            conflict.resolution = f"Consensus: {conflict.positions[0]}"
        conflict.resolved = True

    def _resolve_major(self, conflict: Conflict, evaluated_list: List[EvaluatedResponse]) -> None:
        if self._third_opinion_fn:
            third = self._third_opinion_fn(f"Resolve conflict: {conflict.topic} between {', '.join(conflict.positions)}")
            conflict.resolution = third
            conflict.resolved = True
        else:
            best_idx = self._find_best_index(conflict.models, evaluated_list)
            if best_idx is not None:
                conflict.resolution = f"Adopted from {evaluated_list[best_idx].response.model_id}: {evaluated_list[best_idx].response.response_text[:200]}"
                conflict.resolved = True

    def _find_best_index(self, model_ids: List[str], evaluated_list: List[EvaluatedResponse]) -> Optional[int]:
        best_score = -1.0
        best_idx = None
        for i, ev in enumerate(evaluated_list):
            if ev.response.model_id in model_ids and ev.adjusted_score > best_score:
                best_score = ev.adjusted_score
                best_idx = i
        return best_idx

    def set_third_opinion_fn(self, fn: Callable[[str], str]) -> None:
        self._third_opinion_fn = fn
