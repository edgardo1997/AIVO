"""EventIntelligencePipeline — Escucha eventos del sistema y alimenta la capa de inteligencia.

Traduce eventos del EventBus a métricas procesables para:
  - PerformanceIntelligence (latencia, éxito)
  - FeedbackEngine (calidad percibida)
  - ModelRanking (puntuación dinámica)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class IntelligenceEvent:
    """Evento traducido para la capa de inteligencia."""
    source: str
    event_type: str
    model_id: str
    latency: float
    success: bool
    tokens: int = 0
    cost: float = 0.0
    task_type: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class EventIntelligencePipeline:
    """Escucha eventos del EventBus y actualiza los módulos de inteligencia.

    Suscripciones automáticas:
      - tool_execution.completed  → PerformanceIntelligence
      - model_response.completed  → PerformanceIntelligence + ModelRanking
      - workflow.finished         → FeedbackEngine
      - task.failed               → PerformanceIntelligence + FeedbackEngine
    """

    def __init__(
        self,
        performance_intelligence: Any = None,
        feedback_engine: Any = None,
        model_ranking: Any = None,
        event_bus: Any = None,
    ):
        self._perf = performance_intelligence
        self._feedback = feedback_engine
        self._ranking = model_ranking
        self._event_bus = event_bus
        self._subscribed = False
        self._events_processed: int = 0
        self._last_event: Optional[IntelligenceEvent] = None

    @property
    def events_processed(self) -> int:
        return self._events_processed

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        if self._subscribed:
            return
        if self._event_bus is None:
            logger.warning("No EventBus — intelligence pipeline cannot start")
            return
        try:
            self._event_bus.subscribe("tool_execution.completed", self._on_tool_execution)
            self._event_bus.subscribe("model_response.completed", self._on_model_response)
            self._event_bus.subscribe("workflow.finished", self._on_workflow_finished)
            self._event_bus.subscribe("task.failed", self._on_task_failed)
            self._subscribed = True
            logger.info("EventIntelligencePipeline started — listening for intelligence events")
        except Exception as e:
            logger.warning("Event subscription failed: %s", e)

    def stop(self) -> None:
        if not self._subscribed or self._event_bus is None:
            return
        try:
            self._event_bus.unsubscribe("tool_execution.completed", self._on_tool_execution)
            self._event_bus.unsubscribe("model_response.completed", self._on_model_response)
            self._event_bus.unsubscribe("workflow.finished", self._on_workflow_finished)
            self._event_bus.unsubscribe("task.failed", self._on_task_failed)
        except Exception as e:
            logger.warning("Event unsubscription failed: %s", e)
        self._subscribed = False

    # ── Event handlers ────────────────────────────────────────

    async def _on_tool_execution(self, event: Any) -> None:
        ievent = self._parse_event(event, "tool_execution.completed")
        if ievent is None:
            return
        self._record_performance(ievent)
        self._events_processed += 1
        self._last_event = ievent

    async def _on_model_response(self, event: Any) -> None:
        ievent = self._parse_event(event, "model_response.completed")
        if ievent is None:
            return
        self._record_performance(ievent)
        self._update_ranking(ievent)
        self._events_processed += 1
        self._last_event = ievent

    async def _on_workflow_finished(self, event: Any) -> None:
        ievent = self._parse_event(event, "workflow.finished")
        if ievent is None:
            return
        self._record_feedback(ievent)
        self._events_processed += 1
        self._last_event = ievent

    async def _on_task_failed(self, event: Any) -> None:
        ievent = self._parse_event(event, "task.failed")
        if ievent is None:
            return
        self._record_performance(ievent)
        self._record_feedback(ievent)
        self._events_processed += 1
        self._last_event = ievent

    # ── Intelligence recording ────────────────────────────────

    def _record_performance(self, event: IntelligenceEvent) -> None:
        if self._perf is None:
            return
        try:
            if hasattr(self._perf, "record_metric"):
                self._perf.record_metric({
                    "model_id": event.model_id,
                    "task_type": event.task_type,
                    "latency": event.latency,
                    "success": event.success,
                    "tokens": event.tokens,
                    "cost": event.cost,
                    "timestamp": event.timestamp,
                })
        except Exception as e:
            logger.warning("Performance recording failed: %s", e)

    def _update_ranking(self, event: IntelligenceEvent) -> None:
        if self._ranking is None:
            return
        try:
            if hasattr(self._ranking, "update_score"):
                self._ranking.update_score(
                    model_id=event.model_id,
                    latency=event.latency,
                    success=event.success,
                    task_type=event.task_type,
                )
        except Exception as e:
            logger.warning("Ranking update failed: %s", e)

    def _record_feedback(self, event: IntelligenceEvent) -> None:
        if self._feedback is None:
            return
        try:
            if hasattr(self._feedback, "record_outcome"):
                self._feedback.record_outcome(
                    model_id=event.model_id,
                    task_type=event.task_type,
                    success=event.success,
                    latency=event.latency,
                    error=event.error,
                )
        except Exception as e:
            logger.warning("Feedback recording failed: %s", e)

    # ── Helpers ───────────────────────────────────────────────

    def _parse_event(self, event: Any, event_type: str) -> Optional[IntelligenceEvent]:
        if event is None:
            return None
        data = event.to_dict() if hasattr(event, "to_dict") else (event if isinstance(event, dict) else {})
        return IntelligenceEvent(
            source=data.get("component", "unknown"),
            event_type=event_type,
            model_id=data.get("model_id", data.get("model", data.get("tool_id", "unknown"))),
            latency=float(data.get("duration", data.get("latency", 0))),
            success=bool(data.get("success", data.get("status") == "completed")),
            tokens=int(data.get("tokens", 0)),
            cost=float(data.get("cost", 0)),
            task_type=data.get("task_type", data.get("task", "")),
            error=data.get("error"),
            metadata=data,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
