from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceScore:
    model_id: str = ""
    provider: str = ""
    overall: float = 0.0
    reasoning_quality: float = 0.0
    instruction_adherence: float = 0.0
    coherence: float = 0.0
    evidence_use: float = 0.0
    error_count: int = 0
    detail_level: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "overall": self.overall,
            "reasoning_quality": self.reasoning_quality,
            "instruction_adherence": self.instruction_adherence,
            "coherence": self.coherence,
            "evidence_use": self.evidence_use,
            "error_count": self.error_count,
            "detail_level": self.detail_level,
        }


ERROR_PATTERNS = [
    r"(?i)\b(sorry|apologize|i cannot|i can't|unable to)\b",
    r"(?i)\b(error|failed|incorrect|wrong)\b",
    r"(?i)\b(i don't know|i'm not sure|not certain)\b",
]

VAGUE_PATTERNS = [
    r"(?i)\b(maybe|perhaps|possibly|might be|could be)\b",
    r"(?i)\b(somewhat|kind of|sort of|generally)\b",
    r"(?i)\b(i think|i believe|in my opinion)\b",
]

SPECIFICITY_PATTERNS = [
    (r"(?i)\b(because|therefore|thus|hence|since)\b", 0.1),
    (r"(?i)\b(for example|for instance|specifically|namely)\b", 0.15),
    (r"(?i)\b(\d+\.\d+|\d+%|\d+ ms|\d+ gb)\b", 0.1),
    (r"(?i)\b(according to|based on|reference|source|study)\b", 0.1),
    (r"(?i)\b(first|second|third|finally|next|then)\b", 0.05),
]


class ConfidenceScorer:
    def __init__(self, historical_data: Optional[Dict[str, float]] = None):
        self._model_history: Dict[str, float] = historical_data or {}

    def score(self, response: str, instruction: str = "", model_id: str = "", provider: str = "") -> ConfidenceScore:
        reasoning_quality = self._score_reasoning_quality(response)
        coherence = self._score_coherence(response)
        instruction_adherence = self._score_instruction_adherence(response, instruction)
        evidence_use = self._score_evidence_use(response)
        error_count = self._count_errors(response)
        detail_level = self._score_detail_level(response)
        historical_boost = self._model_history.get(model_id, 0.0)
        overall = (
            reasoning_quality * 0.30 +
            coherence * 0.20 +
            instruction_adherence * 0.20 +
            evidence_use * 0.10 +
            detail_level * 0.10 +
            historical_boost * 0.10
        )
        if error_count > 0:
            overall *= max(0.3, 1.0 - error_count * 0.15)
        return ConfidenceScore(
            model_id=model_id, provider=provider,
            overall=round(min(1.0, overall), 4),
            reasoning_quality=round(reasoning_quality, 4),
            coherence=round(coherence, 4),
            instruction_adherence=round(instruction_adherence, 4),
            evidence_use=round(evidence_use, 4),
            error_count=error_count,
            detail_level=round(detail_level, 4),
        )

    def _score_reasoning_quality(self, text: str) -> float:
        words = text.split()
        if len(words) < 10:
            return 0.3
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return 0.3
        avg_sentence_len = len(words) / len(sentences)
        structural_words = sum(1 for w in words if w.lower() in {"because", "therefore", "however", "although", "consequently", "furthermore", "nevertheless", "moreover", "conversely", "accordingly"})
        structure_score = min(1.0, structural_words / max(1, len(sentences)) * 2)
        length_score = min(1.0, avg_sentence_len / 25.0)
        return 0.3 + structure_score * 0.4 + length_score * 0.3

    def _score_coherence(self, text: str) -> float:
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) < 2:
            return 0.5
        transitions = sum(1 for s in sentences for t in ["however", "therefore", "moreover", "furthermore", "additionally", "consequently", "nevertheless", "meanwhile", "subsequently", "in contrast", "as a result"] if t in s.lower())
        transition_score = min(1.0, transitions / len(sentences) * 1.5)
        consistent_tense = True
        has_repetition = self._check_repetition(sentences)
        repetition_penalty = 0.3 if has_repetition else 0.0
        return max(0.1, min(1.0, 0.4 + transition_score * 0.4 - repetition_penalty))

    def _check_repetition(self, sentences: List[str]) -> bool:
        if len(sentences) < 3:
            return False
        unique_start_words = set(s.split()[0].lower() if s.split() else "" for s in sentences)
        return len(unique_start_words) < len(sentences) * 0.4

    def _score_instruction_adherence(self, response: str, instruction: str) -> float:
        if not instruction:
            return 0.7
        response_lower = response.lower()
        instruction_lower = instruction.lower()
        key_terms = set(re.findall(r'\b[a-zA-Z]{4,}\b', instruction_lower))
        if not key_terms:
            return 0.7
        terms_found = sum(1 for term in key_terms if term in response_lower)
        adherence = terms_found / len(key_terms)
        return min(1.0, 0.3 + adherence * 0.7)

    def _score_evidence_use(self, text: str) -> float:
        evidence_count = 0
        for pattern, weight in SPECIFICITY_PATTERNS:
            if re.search(pattern, text):
                evidence_count += weight
        has_examples = bool(re.search(r"(?i)\b(e\.g\.|i\.e\.|example|instance|like|such as)\b", text))
        example_bonus = 0.15 if has_examples else 0.0
        return min(1.0, evidence_count + example_bonus)

    def _count_errors(self, text: str) -> int:
        count = 0
        for pattern in ERROR_PATTERNS:
            count += len(re.findall(pattern, text))
        for pattern in VAGUE_PATTERNS:
            count += len(re.findall(pattern, text)) * 2
        return count

    def _score_detail_level(self, text: str) -> float:
        words = text.split()
        word_count = len(words)
        if word_count < 20:
            return 0.2
        if word_count < 50:
            return 0.4
        if word_count < 100:
            return 0.6
        if word_count < 200:
            return 0.8
        return 1.0

    def update_model_history(self, model_id: str, score: float) -> None:
        old = self._model_history.get(model_id, 0.0)
        self._model_history[model_id] = old * 0.7 + score * 0.3
