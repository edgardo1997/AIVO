"""Feedback Engine.

Receives user ratings, corrections, and task success/failure signals.
Adjusts model scores based on real user experience.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sentinel.core.event_bus import EventBus
from sentinel.core.event_types import USER_FEEDBACK_RECEIVED
from sentinel.core.events import SentinelEvent

logger = logging.getLogger(__name__)


class FeedbackScore(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class UserFeedback:
    model_id: str
    task_type: str
    score: FeedbackScore
    comment: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task_type": self.task_type,
            "score": self.score.value,
            "comment": self.comment,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
        }


@dataclass
class FeedbackSummary:
    model_id: str
    task_type: str
    total: int
    positive: int
    negative: int
    neutral: int
    positive_ratio: float
    net_score: int

    @property
    def score_delta(self) -> float:
        return round((self.positive - self.negative) / max(self.total, 1) * 100, 1)


class FeedbackEngine:
    def __init__(self, event_bus: Optional[EventBus] = None, max_history: int = 10000):
        self._event_bus = event_bus
        self._max_history = max_history
        self._feedback: List[UserFeedback] = []
        self._subscribed = False

    @property
    def total_feedback(self) -> int:
        return len(self._feedback)

    def subscribe_to_events(self) -> None:
        if self._subscribed or self._event_bus is None:
            return
        self._event_bus.subscribe(USER_FEEDBACK_RECEIVED, self._on_user_feedback)
        self._subscribed = True
        logger.info("FeedbackEngine subscribed to feedback events")

    def record_feedback(self, feedback: UserFeedback) -> None:
        if not feedback.timestamp:
            feedback.timestamp = datetime.now(timezone.utc).isoformat()
        self._feedback.append(feedback)
        if len(self._feedback) > self._max_history:
            self._feedback.pop(0)
        logger.info(
            "Feedback: %s/%s score=%s user=%s",
            feedback.model_id, feedback.task_type, feedback.score.value, feedback.user_id or "anonymous",
        )
        if self._event_bus:
            import asyncio
            try:
                asyncio.ensure_future(
                    self._event_bus.emit(
                        SentinelEvent.new(
                            event_type=USER_FEEDBACK_RECEIVED,
                            session_id=feedback.user_id or "anonymous",
                            request_id=feedback.conversation_id or "",
                            component="feedback_engine",
                            details=feedback.to_dict(),
                        )
                    )
                )
            except Exception:
                logger.warning("Failed to emit user feedback event", exc_info=True)

    def get_summary(
        self, model_id: Optional[str] = None, task_type: Optional[str] = None
    ) -> List[FeedbackSummary]:
        filtered = self._feedback
        if model_id:
            filtered = [f for f in filtered if f.model_id == model_id]
        if task_type:
            filtered = [f for f in filtered if f.task_type == task_type]

        groups: Dict[tuple, List[UserFeedback]] = defaultdict(list)
        for f in filtered:
            key = (f.model_id, f.task_type)
            groups[key].append(f)

        result = []
        for (mid, tt), records in groups.items():
            total = len(records)
            positive = sum(1 for r in records if r.score == FeedbackScore.POSITIVE)
            negative = sum(1 for r in records if r.score == FeedbackScore.NEGATIVE)
            neutral = sum(1 for r in records if r.score == FeedbackScore.NEUTRAL)
            result.append(
                FeedbackSummary(
                    model_id=mid,
                    task_type=tt,
                    total=total,
                    positive=positive,
                    negative=negative,
                    neutral=neutral,
                    positive_ratio=positive / total if total else 0.0,
                    net_score=positive - negative,
                )
            )
        result.sort(key=lambda s: s.positive_ratio, reverse=True)
        return result

    def get_model_feedback(self, model_id: str) -> List[UserFeedback]:
        return [f for f in self._feedback if f.model_id == model_id]

    def get_positive_ratio(self, model_id: str, task_type: Optional[str] = None) -> float:
        summaries = self.get_summary(model_id=model_id, task_type=task_type)
        return summaries[0].positive_ratio if summaries else 0.5

    def clear(self) -> None:
        self._feedback.clear()

    async def _on_user_feedback(self, event: SentinelEvent) -> None:
        details = event.details or {}
        try:
            score = FeedbackScore(details.get("score", "neutral"))
        except ValueError:
            score = FeedbackScore.NEUTRAL
        self.record_feedback(
            UserFeedback(
                model_id=details.get("model_id", "unknown"),
                task_type=details.get("task_type", "unknown"),
                score=score,
                comment=details.get("comment"),
                user_id=details.get("user_id"),
                conversation_id=details.get("conversation_id"),
            )
        )
