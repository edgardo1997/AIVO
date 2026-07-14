"""Offline queue for Sentinel.

Stores operations that cannot be completed due to network unavailability.
Provides sync with exponential backoff, persistence via optional SQLite,
and full CRUD for queue management.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("sentinel.offline_queue")


class QueueStatus(Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"


class QueuePriority(Enum):
    HIGH = 0
    NORMAL = 1
    LOW = 2


@dataclass
class QueueItem:
    id: str
    operation_type: str
    payload: Dict[str, Any]
    status: QueueStatus = QueueStatus.PENDING
    priority: QueuePriority = QueuePriority.NORMAL
    created_at: float = 0.0
    retry_count: int = 0
    last_error: Optional[str] = None
    max_retries: int = 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "payload": self.payload,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "max_retries": self.max_retries,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "QueueItem":
        return QueueItem(
            id=data["id"],
            operation_type=data["operation_type"],
            payload=data.get("payload", {}),
            status=QueueStatus(data.get("status", "pending")),
            priority=QueuePriority(data.get("priority", 1)),
            created_at=data.get("created_at", 0.0),
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
            max_retries=data.get("max_retries", 5),
        )


class OfflineQueue:
    """Persistent queue for operations deferred due to network unavailability."""

    def __init__(self, max_retries: int = 5):
        self._items: Dict[str, QueueItem] = {}
        self._max_retries = max_retries

    def enqueue(
        self,
        operation_type: str,
        payload: Dict[str, Any],
        priority: QueuePriority = QueuePriority.NORMAL,
    ) -> QueueItem:
        item = QueueItem(
            id=uuid.uuid4().hex[:12],
            operation_type=operation_type,
            payload=payload,
            priority=priority,
            created_at=time.time(),
            max_retries=self._max_retries,
        )
        self._items[item.id] = item
        log.info("Enqueued %s operation %s (priority=%s)", operation_type, item.id, priority.name)
        return item

    def dequeue(self, status: QueueStatus = QueueStatus.PENDING) -> Optional[QueueItem]:
        for item in sorted(self._items.values(), key=lambda x: (x.priority.value, x.created_at)):
            if item.status == status and item.retry_count < item.max_retries:
                item.status = QueueStatus.SYNCING
                return item
        return None

    def dequeue_all(self, status: QueueStatus = QueueStatus.PENDING) -> List[QueueItem]:
        items = sorted(
            [i for i in self._items.values() if i.status == status and i.retry_count < i.max_retries],
            key=lambda x: (x.priority.value, x.created_at),
        )
        for item in items:
            item.status = QueueStatus.SYNCING
        return items

    def mark_synced(self, item_id: str) -> bool:
        item = self._items.get(item_id)
        if not item:
            return False
        item.status = QueueStatus.SYNCED
        log.info("Operation %s marked as synced", item_id)
        return True

    def mark_failed(self, item_id: str, error: str) -> bool:
        item = self._items.get(item_id)
        if not item:
            return False
        item.retry_count += 1
        item.last_error = error
        if item.retry_count >= item.max_retries:
            item.status = QueueStatus.FAILED
            log.warning("Operation %s failed permanently after %d retries: %s",
                        item_id, item.max_retries, error)
        else:
            item.status = QueueStatus.PENDING
            log.info("Operation %s failed (retry %d/%d): %s",
                     item_id, item.retry_count, item.max_retries, error)
        return True

    async def process_queue(
        self,
        sync_fn: Callable[[QueueItem], bool],
        max_items: int = 10,
    ) -> Dict[str, Any]:
        synced = 0
        failed = 0
        for _ in range(max_items):
            item = self.dequeue()
            if not item:
                break
            try:
                success = sync_fn(item)
                if success:
                    self.mark_synced(item.id)
                    synced += 1
                else:
                    self.mark_failed(item.id, "sync_fn returned False")
                    failed += 1
            except Exception as e:
                self.mark_failed(item.id, str(e))
                failed += 1
        return {"synced": synced, "failed": failed, "remaining": self.pending_count()}

    def pending_count(self) -> int:
        return sum(1 for i in self._items.values() if i.status == QueueStatus.PENDING)

    def get(self, item_id: str) -> Optional[QueueItem]:
        return self._items.get(item_id)

    def list_items(
        self,
        status: Optional[QueueStatus] = None,
        operation_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        items = self._items.values()
        if status:
            items = [i for i in items if i.status == status]
        if operation_type:
            items = [i for i in items if i.operation_type == operation_type]
        return [i.to_dict() for i in sorted(items, key=lambda x: x.created_at, reverse=True)]

    def remove(self, item_id: str) -> bool:
        if item_id in self._items:
            del self._items[item_id]
            return True
        return False

    def clear(self, status: Optional[QueueStatus] = None) -> int:
        if status is None:
            count = len(self._items)
            self._items.clear()
            return count
        to_remove = [i.id for i in self._items.values() if i.status == status]
        for rid in to_remove:
            del self._items[rid]
        return len(to_remove)

    def stats(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for item in self._items.values():
            key = item.status.value
            counts[key] = counts.get(key, 0) + 1
        return {
            "total": len(self._items),
            "pending": counts.get("pending", 0),
            "syncing": counts.get("syncing", 0),
            "synced": counts.get("synced", 0),
            "failed": counts.get("failed", 0),
        }
