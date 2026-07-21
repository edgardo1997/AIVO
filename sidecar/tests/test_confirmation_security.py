"""Tests for confirmation security: expiration, replay, identity change, tampering."""

import time
import uuid
from datetime import datetime, timezone

import pytest
from sentinel.core.confirmation import ConfirmationBroker
from sentinel.core.operational_memory import InMemoryBackend, OperationalMemoryConfig


@pytest.fixture
def memory():
    config = OperationalMemoryConfig(max_pending_actions=100)
    backend = InMemoryBackend(config=config)
    backend._stop_eviction.set()
    yield backend


@pytest.fixture
def broker(memory):
    return ConfirmationBroker(memory, ttl_seconds=60)


class TestConfirmationSecurity:
    def test_request_creates_approval(self, broker, memory):
        aid = broker.request("filesystem.write", {"path": "/test"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "user request", risk_level="medium", plan_id="plan-1")
        record = memory.get_pending_action(aid)
        assert record is not None
        assert record.risk_level == "medium"
        assert record.plan_id == "plan-1"
        assert record.redacted
        assert record.params_hash

    def test_consume_approves_and_removes(self, broker, memory):
        aid = broker.request("filesystem.write", {"path": "/test"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "test")
        grant = broker.consume(aid, "alice", approved=True)
        assert grant is not None
        assert grant.tool_id == "filesystem.write"
        assert grant.user_id == "alice"
        assert memory.get_pending_action(aid) is None

    def test_consume_denied_removes(self, broker, memory):
        aid = broker.request("filesystem.write", {"path": "/test"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "test")
        grant = broker.consume(aid, "alice", approved=False)
        assert grant is None
        assert memory.get_pending_action(aid) is None

    def test_replay_rejected(self, broker, memory):
        aid = broker.request("filesystem.write", {"path": "/test"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "test")
        # First consume succeeds
        grant = broker.consume(aid, "alice", approved=True)
        assert grant is not None
        # Second consume on same action_id returns None (already removed)
        grant2 = broker.consume(aid, "alice", approved=True)
        assert grant2 is None

    def test_wrong_user_rejected(self, broker):
        aid = broker.request("filesystem.delete", {"path": "/etc"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "test")
        with pytest.raises(PermissionError, match="Identity hash mismatch"):
            broker.consume(aid, "mallory", approved=True)

    def test_expired_approval_rejected(self, memory):
        broker = ConfirmationBroker(memory, ttl_seconds=0)
        aid = broker.request("executor.command", {"command": "rm"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "test")
        time.sleep(0.1)
        grant = broker.consume(aid, "alice", approved=True)
        assert grant is None

    def test_tampered_params_rejected(self, broker, memory):
        aid = broker.request("filesystem.write", {"path": "/safe/file"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "test")
        # Tamper with stored params
        record = memory.get_pending_action(aid)
        record.params["params"]["path"] = "/etc/passwd"
        with pytest.raises(PermissionError, match="tampered"):
            broker.consume(aid, "alice", approved=True)

    def test_identity_change_detected(self, broker, memory):
        aid = broker.request("filesystem.write", {"path": "/test"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "test")
        record = memory.get_pending_action(aid)
        record.params["user_id"] = "mallory"
        with pytest.raises(PermissionError, match="Identity hash mismatch"):
            broker.consume(aid, "mallory", approved=True)

    def test_approval_metadata(self, broker):
        aid = broker.request(
            "executor.command", {"command": "shutdown"},
            {"identity": {"user_id": "bob", "role": "admin"}},
            "shutdown requested",
            risk_level="high",
            plan_id="plan-shutdown-1",
        )
        peek = broker.peek(aid)
        assert peek is not None
        assert peek["risk_level"] == "high"
        assert peek["plan_id"] == "plan-shutdown-1"
        assert peek["tool_id"] == "executor.command"
        assert peek["redacted"]

    def test_peek_nonexistent(self, broker):
        assert broker.peek("no-such-id") is None

    def test_consume_nonexistent(self, broker):
        grant = broker.consume("no-such-id", "alice", approved=True)
        assert grant is None

    def test_request_no_identity_raises(self, broker):
        with pytest.raises(ValueError, match="user"):
            broker.request("filesystem.write", {}, {}, "test")

    def test_redacts_secrets_in_params(self, broker, memory):
        aid = broker.request("ai.config", {
            "api_key": "sk-secret-12345",
            "model": "gpt-4",
        }, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "config change")
        record = memory.get_pending_action(aid)
        stored_api_key = record.params["params"].get("api_key", "")
        assert "sk-secret" not in stored_api_key
        assert stored_api_key == "<REDACTED>"

    def test_risk_and_plan_in_grant(self, broker):
        aid = broker.request("executor.launch", {"target": "server"}, {
            "identity": {"user_id": "alice", "role": "user"},
        }, "launch", risk_level="high", plan_id="plan-launch-1")
        grant = broker.consume(aid, "alice", approved=True)
        assert grant is not None
        assert grant.risk_level == "high"
        assert grant.plan_id == "plan-launch-1"
