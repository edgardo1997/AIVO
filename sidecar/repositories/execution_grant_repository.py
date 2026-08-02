"""Durable, conditional state transitions for plan and step grants."""
import json
from datetime import datetime, timezone

from .database import DatabaseManager


class ExecutionGrantRepository:
    def __init__(self, db=None):
        self._db = db or DatabaseManager()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def create_plan(self, grant: dict) -> bool:
        required = ("grant_id", "user_id", "session_id", "identity_hash", "plan_id", "plan_hash", "plan_payload", "risk_level", "expires_at")
        if any(not grant.get(key) for key in required):
            raise ValueError("incomplete plan grant")
        now = self._now()
        with self._db.transaction(immediate=True) as conn:
            conn.execute("""INSERT INTO plan_approval_grants
                (grant_id,user_id,session_id,identity_hash,plan_id,plan_hash,plan_payload,risk_level,simulation_evidence,schema_version,status,created_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?, 'pending',?,?)""", (
                *(grant[key] for key in required[:8]), json.dumps(grant.get("simulation_evidence", {}), sort_keys=True), grant.get("schema_version", 1), now, grant["expires_at"]
            ))
            self._audit(conn, grant["grant_id"], "plan", "created", grant)
        return True

    def transition_plan(self, grant_id: str, expected: str, target: str, actor: dict) -> bool:
        if (expected, target) not in {
            ("pending", "approved"), ("approved", "in_progress"),
            ("in_progress", "consumed"), ("pending", "rejected"),
            ("pending", "cancelled"), ("approved", "cancelled"),
            ("in_progress", "failed"),
        }:
            return False
        actor = actor or {}
        now = self._now()
        with self._db.transaction(immediate=True) as conn:
            row = conn.execute("SELECT * FROM plan_approval_grants WHERE grant_id=?", (grant_id,)).fetchone()
            if not row:
                return False
            if row["expires_at"] <= now and row["status"] in ("pending", "approved", "in_progress"):
                conn.execute("UPDATE plan_approval_grants SET status='expired' WHERE grant_id=? AND status=?", (grant_id, row["status"]))
                self._audit(conn, grant_id, "plan", "expired", actor)
                return False
            column = {"approved": "approved_at", "consumed": "consumed_at", "rejected": "rejected_at"}.get(target)
            sql = "UPDATE plan_approval_grants SET status=?" + (f", {column}=?" if column else "") + " WHERE grant_id=? AND status=? AND expires_at>?"
            params = (target, now, grant_id, expected, now) if column else (target, grant_id, expected, now)
            if conn.execute(sql, params).rowcount != 1:
                self._audit(conn, grant_id, "plan", "transition_rejected", {**actor, "expected": expected, "target": target})
                return False
            self._audit(conn, grant_id, "plan", target, actor)
            return True

    def get_plan(self, grant_id: str):
        return self._db.fetchone("SELECT * FROM plan_approval_grants WHERE grant_id=?", (grant_id,))

    def create_step(self, grant: dict) -> bool:
        required = ("step_grant_id", "plan_grant_id", "plan_id", "plan_hash", "step_id", "step_index", "tool_id", "params_hash", "identity_hash", "session_id", "expires_at")
        if any(grant.get(key) in (None, "") for key in required):
            raise ValueError("incomplete step grant")
        with self._db.transaction(immediate=True) as conn:
            parent = conn.execute("SELECT status,plan_id,plan_hash,identity_hash,session_id FROM plan_approval_grants WHERE grant_id=?", (grant["plan_grant_id"],)).fetchone()
            if not parent or parent["status"] not in ("approved", "in_progress"):
                return False
            if any(parent[key] != grant[key] for key in ("plan_id", "plan_hash", "identity_hash", "session_id")):
                return False
            conn.execute("""INSERT INTO step_execution_grants
                (step_grant_id,plan_grant_id,plan_id,plan_hash,step_id,step_index,tool_id,params_hash,identity_hash,session_id,status,created_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?, 'approved',?,?)""", tuple(grant[key] for key in required[:-1]) + (self._now(), grant["expires_at"]))
            self._audit(conn, grant["step_grant_id"], "step", "created", grant)
        return True

    def consume_step(self, step_grant_id: str, binding: dict) -> bool:
        now = self._now()
        required = ("plan_grant_id", "plan_id", "plan_hash", "step_id", "step_index", "tool_id", "params_hash", "identity_hash", "session_id")
        if any(binding.get(key) in (None, "") for key in required):
            return False
        with self._db.transaction(immediate=True) as conn:
            sql = """UPDATE step_execution_grants SET status='consumed', consumed_at=?
                     WHERE step_grant_id=? AND status='approved' AND expires_at>?
                       AND plan_grant_id=? AND plan_id=? AND plan_hash=? AND step_id=? AND step_index=? AND tool_id=?
                       AND params_hash=? AND identity_hash=? AND session_id=?"""
            params = (now, step_grant_id, now, *(binding[key] for key in required))
            if conn.execute(sql, params).rowcount != 1:
                self._audit(conn, step_grant_id, "step", "replay_or_mismatch", binding)
                return False
            self._audit(conn, step_grant_id, "step", "consumed", binding)
            return True

    def get_step(self, step_grant_id: str):
        return self._db.fetchone("SELECT * FROM step_execution_grants WHERE step_grant_id=?", (step_grant_id,))

    def _audit(self, conn, grant_id, kind, event, details):
        details = details or {}
        metadata = details.get("metadata", {})
        conn.execute(
            """INSERT INTO execution_grant_audit
               (grant_id,grant_kind,event_type,occurred_at,actor_user_id,session_id,identity_hash,plan_id,step_id,tool_id,reason,metadata_redacted)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                grant_id, kind, event, self._now(), str(details.get("user_id", "")),
                str(details.get("session_id", "")), str(details.get("identity_hash", "")),
                str(details.get("plan_id", "")), str(details.get("step_id", "")),
                str(details.get("tool_id", "")), str(details.get("reason", "")),
                json.dumps(metadata, sort_keys=True, default=str),
            ),
        )
