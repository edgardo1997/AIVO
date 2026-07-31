from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging
import re

from sentinel.intelligence.evaluation_engine import EvaluatedResponse, EvaluationEngine
from sentinel.intelligence.conflict_resolver import ConflictResolver, ConflictReport

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    final_answer: str = ""
    confidence: float = 0.0
    primary_model: str = ""
    primary_provider: str = ""
    contributing_models: List[str] = field(default_factory=list)
    total_evaluated: int = 0
    conflict_report: Optional[ConflictReport] = None
    score_breakdown: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer[:1000],
            "confidence": self.confidence,
            "primary_model": self.primary_model,
            "primary_provider": self.primary_provider,
            "contributing_models": list(self.contributing_models),
            "total_evaluated": self.total_evaluated,
            "conflict_report": self.conflict_report.to_dict() if self.conflict_report else None,
            "score_breakdown": list(self.score_breakdown),
        }


IMPORTANT_SENTENCE_PATTERNS = [
    r"(?i)(?:in conclusion|to summarize|overall|the answer is|therefore|thus)\s*:\s*(.+?)(?:\.|$)",
    r"(?i)(?:the (?:main|key|primary|most important)\s+\w+\s+is\s+)(.+?)(?:\.|$)",
    r"(?i)(?:recommend|suggest|propose)\s+(.+?)(?:\.|$)",
]


def extract_key_sentences(text: str) -> List[str]:
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def extract_conclusion(text: str) -> str:
    paragraphs = text.strip().split("\n\n")
    if len(paragraphs) > 1:
        last = paragraphs[-1].strip()
        if len(last) > 30:
            return last
        second_last = paragraphs[-2].strip() if len(paragraphs) > 1 else last
        if len(second_last) > 30:
            return second_last
    for pattern in IMPORTANT_SENTENCE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    sentences = extract_key_sentences(text)
    return sentences[-1] if sentences else text[:300]


class ConsensusEngine:
    def __init__(self, evaluation_engine: EvaluationEngine, conflict_resolver: Optional[ConflictResolver] = None):
        self._evaluator = evaluation_engine
        self._conflict_resolver = conflict_resolver or ConflictResolver()

    def build_consensus(self, evaluated_list: List[EvaluatedResponse], instruction: str = "") -> ConsensusResult:
        if not evaluated_list:
            return ConsensusResult(final_answer="", confidence=0.0)
        ranked = self._evaluator.rank(evaluated_list)
        best = ranked[0]
        conflict_report = self._conflict_resolver.resolve(evaluated_list)
        final_answer = self._synthesize_answer(best, ranked, conflict_report, instruction)
        confidence = self._compute_consensus_confidence(ranked, conflict_report)
        return ConsensusResult(
            final_answer=final_answer,
            confidence=round(confidence, 4),
            primary_model=best.response.model_id,
            primary_provider=best.response.provider,
            contributing_models=[ev.response.model_id for ev in ranked if ev.adjusted_score > 0.3],
            total_evaluated=len(evaluated_list),
            conflict_report=conflict_report,
            score_breakdown=[{"model_id": ev.response.model_id, "provider": ev.response.provider, "adjusted_score": ev.adjusted_score, "confidence": ev.confidence.overall, "duration_ms": ev.response.duration_ms, "cost": ev.response.cost} for ev in ranked],
        )

    def _synthesize_answer(self, best: EvaluatedResponse, ranked: List[EvaluatedResponse], conflict_report: ConflictReport, instruction: str) -> str:
        parts = []
        conclusion = extract_conclusion(best.response.response_text)
        parts.append(f"## Resumen\n\n{best.response.response_text[:500]}")
        if len(ranked) > 1:
            parts.append(f"\n\n## Análisis adicional\n\nSe consultaron {len(ranked)} modelos. {self._format_additional_insights(ranked, best)}")
        if conflict_report and conflict_report.total_conflicts > 0:
            resolved = conflict_report.resolved_count
            total = conflict_report.total_conflicts
            parts.append(f"\n\n## Resolución de conflictos\n\nSe detectaron {total} discrepancia(s), {resolved} resuelta(s).")
            for c in conflict_report.conflicts:
                if c.resolved and c.resolution:
                    parts.append(f"- **{c.topic}**: {c.resolution}")
        return "".join(parts)

    def _format_additional_insights(self, ranked: List[EvaluatedResponse], best: EvaluatedResponse) -> str:
        insights = []
        for ev in ranked[1:3]:
            if ev.adjusted_score > 0.3:
                conclusion = extract_conclusion(ev.response.response_text)
                insights.append(f"**{ev.response.model_id}** (confianza: {ev.confidence.overall:.2f}): {conclusion[:200]}")
        return " ".join(insights) if insights else ""

    def _compute_consensus_confidence(self, ranked: List[EvaluatedResponse], conflict_report: ConflictReport) -> float:
        if not ranked:
            return 0.0
        top_score = ranked[0].adjusted_score
        if len(ranked) == 1:
            return top_score * 0.8
        agreement_factor = 1.0
        if conflict_report and conflict_report.total_conflicts > 0:
            unresolved = conflict_report.unresolved_count
            agreement_factor = max(0.3, 1.0 - unresolved * 0.2)
        avg_score = sum(ev.adjusted_score for ev in ranked) / len(ranked)
        return avg_score * agreement_factor
