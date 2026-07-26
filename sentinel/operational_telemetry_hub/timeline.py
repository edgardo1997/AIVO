"""Persistent ordered view over sanitized operational events."""

from .events import OperationalEventV1
from .storage import OperationalTelemetryStorage


class OperationalTimeline:
    def __init__(self, storage: OperationalTelemetryStorage) -> None:
        self.storage = storage

    def latest(self, limit: int = 100) -> tuple[OperationalEventV1, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("timeline limit must be between 1 and 1000")
        rows = self.storage.connection.execute(
            """
            SELECT event_id FROM timeline_index
            ORDER BY sequence_id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        events = tuple(self.storage.read_event(row["event_id"]) for row in reversed(rows))
        return tuple(event for event in events if event is not None)
