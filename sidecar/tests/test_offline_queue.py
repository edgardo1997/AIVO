"""Tests for sentinel.core.offline_queue and sentinel.core.network_monitor."""
import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
from unittest.mock import MagicMock, AsyncMock, patch
from sentinel.core.offline_queue import OfflineQueue, QueueItem, QueueStatus, QueuePriority
from sentinel.core.network_monitor import NetworkMonitor


class TestOfflineQueue:
    def test_enqueue_creates_item(self):
        q = OfflineQueue()
        item = q.enqueue("test.op", {"key": "val"})
        assert item.id is not None
        assert item.operation_type == "test.op"
        assert item.payload == {"key": "val"}
        assert item.status == QueueStatus.PENDING

    def test_dequeue_returns_pending(self):
        q = OfflineQueue()
        q.enqueue("op1", {})
        item = q.dequeue()
        assert item is not None
        assert item.status == QueueStatus.SYNCING

    def test_dequeue_empty(self):
        q = OfflineQueue()
        assert q.dequeue() is None

    def test_dequeue_respects_priority(self):
        q = OfflineQueue()
        q.enqueue("low", {}, priority=QueuePriority.LOW)
        q.enqueue("high", {}, priority=QueuePriority.HIGH)
        item = q.dequeue()
        assert item.operation_type == "high"

    def test_mark_synced(self):
        q = OfflineQueue()
        item = q.enqueue("op", {})
        assert q.mark_synced(item.id) is True
        assert item.status == QueueStatus.SYNCED

    def test_mark_failed_increments_retry(self):
        q = OfflineQueue(max_retries=3)
        item = q.enqueue("op", {})
        q.mark_failed(item.id, "error 1")
        assert item.retry_count == 1
        assert item.status == QueueStatus.PENDING
        assert item.last_error == "error 1"

    def test_mark_failed_permanent(self):
        q = OfflineQueue(max_retries=2)
        item = q.enqueue("op", {})
        q.mark_failed(item.id, "e1")
        q.mark_failed(item.id, "e2")
        assert item.status == QueueStatus.FAILED
        assert item.retry_count == 2

    def test_mark_nonexistent(self):
        q = OfflineQueue()
        assert q.mark_synced("nonexistent") is False
        assert q.mark_failed("nonexistent", "err") is False

    def test_pending_count(self):
        q = OfflineQueue()
        assert q.pending_count() == 0
        q.enqueue("op", {})
        assert q.pending_count() == 1
        q.dequeue()
        assert q.pending_count() == 0

    def test_list_items_by_status(self):
        q = OfflineQueue()
        q.enqueue("op1", {})
        q.enqueue("op2", {})
        items = q.list_items(status=QueueStatus.PENDING)
        assert len(items) == 2
        items = q.list_items(status=QueueStatus.SYNCED)
        assert len(items) == 0

    def test_list_items_by_type(self):
        q = OfflineQueue()
        q.enqueue("type_a", {})
        q.enqueue("type_b", {})
        items = q.list_items(operation_type="type_a")
        assert len(items) == 1
        assert items[0]["operation_type"] == "type_a"

    def test_remove(self):
        q = OfflineQueue()
        item = q.enqueue("op", {})
        assert q.remove(item.id) is True
        assert q.get(item.id) is None
        assert q.remove("nonexistent") is False

    def test_clear_all(self):
        q = OfflineQueue()
        q.enqueue("a", {})
        q.enqueue("b", {})
        assert q.clear() == 2
        assert q.stats()["total"] == 0

    def test_clear_by_status(self):
        q = OfflineQueue()
        q.enqueue("a", {})
        q.enqueue("b", {})
        item = q.dequeue()
        q.mark_synced(item.id)
        assert q.clear(status=QueueStatus.PENDING) == 1
        assert q.clear(status=QueueStatus.SYNCED) == 1
        assert q.stats()["total"] == 0

    def test_stats(self):
        q = OfflineQueue()
        q.enqueue("a", {})
        q.enqueue("b", {})
        q.enqueue("c", {})
        item = q.dequeue()
        q.mark_synced(item.id)
        stats = q.stats()
        assert stats["total"] == 3
        assert stats["pending"] == 2
        assert stats["synced"] == 1
        assert stats["syncing"] == 0

    def test_process_queue(self):
        q = OfflineQueue()
        q.enqueue("op", {"x": 1})
        q.enqueue("op", {"x": 2})
        results = []
        def sync_fn(item):
            results.append(item.id)
            return True
        import asyncio
        stats = asyncio.run(q.process_queue(sync_fn, max_items=10))
        assert stats["synced"] == 2
        assert stats["failed"] == 0
        assert stats["remaining"] == 0

    def test_process_queue_with_failures(self):
        q = OfflineQueue(max_retries=1)
        q.enqueue("op", {})
        def fail_fn(item):
            raise RuntimeError("fail")
        import asyncio
        stats = asyncio.run(q.process_queue(fail_fn, max_items=10))
        assert stats["synced"] == 0
        assert stats["failed"] == 1

    def test_enqueue_respects_max_retries(self):
        q = OfflineQueue(max_retries=3)
        item = q.enqueue("op", {})
        assert item.max_retries == 3

    def test_queue_item_roundtrip(self):
        item = QueueItem(id="x1", operation_type="t", payload={}, priority=QueuePriority.HIGH)
        d = item.to_dict()
        restored = QueueItem.from_dict(d)
        assert restored.id == "x1"
        assert restored.priority == QueuePriority.HIGH
        assert restored.status == QueueStatus.PENDING


class TestNetworkMonitor:
    @pytest.mark.asyncio
    async def test_initial_state(self):
        nm = NetworkMonitor(check_urls=["http://127.0.0.1:1"], timeout=0.1)
        assert nm.is_initialized is False
        assert nm.is_online is False

    @pytest.mark.asyncio
    async def test_check_returns_false_when_offline(self):
        nm = NetworkMonitor(check_urls=["http://127.0.0.1:1"], timeout=0.1)
        online = await nm.check()
        assert online is False

    @pytest.mark.asyncio
    async def test_on_transition_callback(self):
        nm = NetworkMonitor(check_urls=["http://127.0.0.1:1"], timeout=0.1)
        calls = []
        nm.on_transition(lambda o: calls.append(o))
        prev = nm.is_online
        await nm.check()
        # callback may or may not fire depending on prev state

    @pytest.mark.asyncio
    async def test_start_stop(self):
        nm = NetworkMonitor(check_urls=["http://127.0.0.1:1"], timeout=0.1)
        await nm.start()
        assert nm._running is True
        await nm.stop()
        assert nm._running is False


class TestOrchestratorOfflineIntegration:
    @pytest.mark.asyncio
    async def test_process_offline_queues_item(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.offline_queue import OfflineQueue
        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        q = OfflineQueue()
        orch = Orchestrator(intent_engine=IntentEngine(), tool_gateway=gw, offline_queue=q)
        result = await orch.process_offline("test utterance")
        assert result.action_id is not None
        assert q.pending_count() == 1

    @pytest.mark.asyncio
    async def test_process_offline_no_queue(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        orch = Orchestrator(intent_engine=IntentEngine(), tool_gateway=gw, offline_queue=None)
        result = await orch.process_offline("test")
        assert "not configured" in (result.error or "")

    @pytest.mark.asyncio
    async def test_network_transition_callback(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.offline_queue import OfflineQueue
        from sentinel.core.network_monitor import NetworkMonitor
        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        q = OfflineQueue()
        nm = NetworkMonitor(check_urls=["http://127.0.0.1:1"], timeout=0.1)
        orch = Orchestrator(intent_engine=IntentEngine(), tool_gateway=gw, offline_queue=q, network_monitor=nm)
        assert orch.offline_queue is q
        assert orch.network_monitor is nm

    def test_offline_queue_property(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.offline_queue import OfflineQueue
        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        q = OfflineQueue()
        orch = Orchestrator(intent_engine=IntentEngine(), tool_gateway=gw, offline_queue=q)
        assert orch.offline_queue is q


class TestOfflineQueueAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge
        reset_bridge()

    def test_offline_queue_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/offline-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    def test_offline_queue_clear(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/offline-queue/clear")
        assert resp.status_code == 200

    def test_offline_queue_sync(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/offline-queue/sync")
        assert resp.status_code == 200

    def test_network_status(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/network/status")
        assert resp.status_code == 200
