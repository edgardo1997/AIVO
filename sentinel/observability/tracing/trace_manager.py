"""Distributed Tracing — TraceID generation and propagation across pipeline components."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging
import threading
import time
import uuid

logger = logging.getLogger(__name__)


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    component: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    status: str = "ok"
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_time > 0:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "component": self.component,
            "start_time": self.start_time,
            "duration_ms": round(self.duration_ms, 1),
            "status": self.status,
            "metadata": self.metadata,
            "tags": self.tags,
        }


class TraceManager:
    """Manages distributed trace context propagation.

    Each request gets a trace_id that travels through Sentinel's pipeline:
      User → IntentEngine → Planner → ModelRouter → ToolGateway
    """

    def __init__(self, max_traces: int = 1000):
        self._traces: Dict[str, List[SpanContext]] = {}
        self._local = threading.local()
        self._max_traces = max_traces
        self._lock = threading.Lock()

    def generate_trace_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def generate_span_id(self) -> str:
        return uuid.uuid4().hex[:8]

    @property
    def current_trace_id(self) -> Optional[str]:
        return getattr(self._local, "trace_id", None)

    @current_trace_id.setter
    def current_trace_id(self, value: Optional[str]) -> None:
        self._local.trace_id = value

    @property
    def current_span_id(self) -> Optional[str]:
        return getattr(self._local, "span_id", None)

    @current_span_id.setter
    def current_span_id(self, value: Optional[str]) -> None:
        self._local.span_id = value

    def start_trace(self, component: str = "runtime", metadata: Optional[Dict[str, Any]] = None) -> SpanContext:
        trace_id = self.generate_trace_id()
        span_id = self.generate_span_id()
        self.current_trace_id = trace_id
        self.current_span_id = span_id
        span = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            component=component,
            start_time=time.monotonic(),
            metadata=metadata or {},
        )
        self._store_span(span)
        return span

    def start_span(self, component: str, metadata: Optional[Dict[str, Any]] = None) -> SpanContext:
        trace_id = self.current_trace_id or self.generate_trace_id()
        parent_span_id = self.current_span_id
        span_id = self.generate_span_id()
        self.current_span_id = span_id
        if not self.current_trace_id:
            self.current_trace_id = trace_id
        span = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            component=component,
            start_time=time.monotonic(),
            metadata=metadata or {},
        )
        self._store_span(span)
        return span

    def end_span(self, span: SpanContext, status: str = "ok", tags: Optional[Dict[str, str]] = None) -> None:
        span.end_time = time.monotonic()
        span.status = status
        if tags:
            span.tags.update(tags)

    def _store_span(self, span: SpanContext) -> None:
        with self._lock:
            tid = span.trace_id
            if tid not in self._traces:
                self._traces[tid] = []
            self._traces[tid].append(span)
            if len(self._traces) > self._max_traces:
                oldest = min(self._traces.keys(), key=lambda k: self._traces[k][0].start_time)
                del self._traces[oldest]

    def get_trace(self, trace_id: str) -> List[SpanContext]:
        with self._lock:
            return list(self._traces.get(trace_id, []))

    def get_all_traces(self, limit: int = 100) -> Dict[str, List[SpanContext]]:
        with self._lock:
            sorted_keys = sorted(self._traces.keys(), key=lambda k: self._traces[k][0].start_time, reverse=True)
            return {k: list(self._traces[k]) for k in sorted_keys[:limit]}

    def get_trace_tree(self, trace_id: str) -> Dict[str, Any]:
        spans = self.get_trace(trace_id)
        if not spans:
            return {"trace_id": trace_id, "spans": [], "total_duration_ms": 0.0}
        total = sum(s.duration_ms for s in spans if s.end_time > 0)
        return {
            "trace_id": trace_id,
            "spans": [s.to_dict() for s in sorted(spans, key=lambda s: s.start_time)],
            "total_duration_ms": round(total, 1),
        }

    def trace_summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._traces)
            spans = sum(len(v) for v in self._traces.values())
            return {"total_traces": total, "total_spans": spans}

    def create_context_from_request(self, request_id: Optional[str] = None) -> SpanContext:
        trace_id = request_id or self.generate_trace_id()
        span_id = self.generate_span_id()
        self.current_trace_id = trace_id
        self.current_span_id = span_id
        span = SpanContext(trace_id=trace_id, span_id=span_id, component="request", start_time=time.monotonic())
        self._store_span(span)
        return span
