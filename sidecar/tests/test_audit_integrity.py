import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from repositories.database import DatabaseManager
from services.audit_service import AuditService


def test_pipeline_payload_round_trips_with_identity():
    service = AuditService()
    service.log_pipeline(
        "exec-123",
        identity={"user_id": "actor-1", "is_authenticated": True},
        intent={"target": "system.info"},
        decision={"decision": "approve"},
        policy={"effect": "allow"},
        execution={"success": True},
        quality={"passed": True},
        tool_id="system.info",
    )

    entry = service.get_log(limit=1)["entries"][0]
    assert entry["execution_id"] == "exec-123"
    assert entry["user"] == "actor-1"
    assert entry["payload"]["pipeline"]["identity"]["user_id"] == "actor-1"
    assert entry["payload"]["pipeline"]["policy"]["effect"] == "allow"
    assert entry["entry_hash"]


def test_database_rejects_audit_update_and_delete():
    service = AuditService()
    before = service.get_log()["total"]
    service.log_action("security.test", "immutable")
    db = DatabaseManager()

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with db.transaction(immediate=True) as conn:
            conn.execute("UPDATE audit_log SET details = 'tampered'")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with db.transaction(immediate=True) as conn:
            conn.execute("DELETE FROM audit_log")

    assert service.get_log()["total"] == before + 1


def test_concurrent_appends_preserve_integrity_chain():
    service = AuditService()
    before = service.verify_integrity()["entries"]

    def append(index: int):
        service.log_action("concurrent.test", f"entry-{index}", user="actor")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(20)))

    integrity = service.verify_integrity()
    assert integrity["valid"] is True
    assert integrity["entries"] == before + 20
    assert len(integrity["head"]) == 64
