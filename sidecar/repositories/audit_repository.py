import hashlib
import json
import uuid

from .database import DatabaseManager

MAX_ENTRIES = 1000

class AuditRepository:
    def __init__(self, db=None):
        self._db = db or DatabaseManager()

    def append(self, entry: dict):
        event_id = entry.get("event_id") or uuid.uuid4().hex
        execution_id = entry.get("execution_id")
        payload = entry.get("payload") or {
            key: value
            for key, value in entry.items()
            if key not in {"timestamp", "action", "details", "status", "user"}
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        details = entry.get("details") or payload_json
        status = entry.get("status", "info")
        user = entry.get("user", "unknown")

        with self._db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT entry_hash FROM audit_log WHERE entry_hash IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous_hash = row["entry_hash"] if row else ""
            canonical = self._canonical_entry(
                timestamp=entry["timestamp"], action=entry["action"], details=details,
                status=status, user=user, event_id=event_id,
                execution_id=execution_id, payload=payload,
                previous_hash=previous_hash,
            )
            entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            conn.execute(
                """INSERT INTO audit_log
                   (timestamp, action, details, status, user, event_id,
                    execution_id, payload, previous_hash, entry_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry["timestamp"], entry["action"], details, status, user,
                 event_id, execution_id, payload_json, previous_hash, entry_hash),
            )
        return {"event_id": event_id, "entry_hash": entry_hash}

    def read_all(self, limit: int = None, action_filter: str = None) -> list:
        sql = "SELECT * FROM audit_log"
        params = []
        if action_filter:
            sql += " WHERE action = ?"
            params.append(action_filter)
        sql += " ORDER BY id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._db.fetchall(sql, tuple(params))
        for row in rows:
            try:
                row["payload"] = json.loads(row.get("payload") or "{}")
            except json.JSONDecodeError:
                row["payload"] = {"corrupt": True}
            # Preserve the v1 response shape while keeping the canonical payload.
            if isinstance(row["payload"], dict):
                if "pipeline" in row["payload"]:
                    row["pipeline"] = row["payload"]["pipeline"]
                if "error" in row["payload"]:
                    row["error"] = row["payload"]["error"]
        return rows

    def count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) AS cnt FROM audit_log")
        return row["cnt"] if row else 0

    def verify_integrity(self) -> dict:
        rows = self._db.fetchall(
            "SELECT * FROM audit_log WHERE entry_hash IS NOT NULL ORDER BY id ASC"
        )
        previous_hash = ""
        for row in rows:
            try:
                payload = json.loads(row.get("payload") or "{}")
            except json.JSONDecodeError:
                return {"valid": False, "event_id": row.get("event_id"), "reason": "invalid_payload"}
            if row.get("previous_hash", "") != previous_hash:
                return {"valid": False, "event_id": row.get("event_id"), "reason": "broken_chain"}
            canonical = self._canonical_entry(
                timestamp=row["timestamp"], action=row["action"], details=row.get("details", ""),
                status=row.get("status", "info"), user=row.get("user", "unknown"),
                event_id=row.get("event_id"), execution_id=row.get("execution_id"),
                payload=payload, previous_hash=previous_hash,
            )
            calculated = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if calculated != row.get("entry_hash"):
                return {"valid": False, "event_id": row.get("event_id"), "reason": "hash_mismatch"}
            previous_hash = calculated
        return {"valid": True, "entries": len(rows), "head": previous_hash}

    @staticmethod
    def _canonical_entry(**fields) -> str:
        return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)

    # Audit is append-only — no clear() or trim() exposed
