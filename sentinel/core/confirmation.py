import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .operational_memory import PendingActionRecord
from repositories.execution_grant_repository import ExecutionGrantRepository
from sentinel.security.models import ExecutionGrantContext


_SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "api-key",
        "x-api-key",
        "auth_token",
        "access_key",
        "secret_key",
        "private_key",
    }
)


@dataclass
class ConfirmationGrant:
    action_id: str
    tool_id: str
    params: Dict[str, Any]
    context: Dict[str, Any]
    user_id: str
    risk_level: str = "unknown"
    plan_id: str = ""
    params_hash: str = ""
    identity_hash: str = ""


class ConfirmationBroker:
    """Persistent, identity-bound, single-use confirmation broker.

    Binds each approval to: user, tool, params, risk, plan, expiration,
    single-use identifier. Rejects expired, replayed, or tampered approvals.
    """

    def __init__(self, memory, ttl_seconds: int = 600):
        self._memory = memory
        self._ttl_seconds = ttl_seconds
        # Inactive until every production consumer supplies a grant_id.
        self._grants = ExecutionGrantRepository()

    @staticmethod
    def _hash(obj: Any) -> str:
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def canonical_params_hash(cls, *, tool_id: str, params: Dict[str, Any], plan_id: str, identity_hash: str) -> str:
        """Stable binding for an execution effect; key order cannot alter it."""
        return cls._hash({"tool_id": tool_id, "params": params, "plan_id": plan_id, "identity_hash": identity_hash})

    @staticmethod
    def canonical_plan(plan: Dict[str, Any]) -> tuple[str, str]:
        """Persist an immutable, deterministic plan representation."""
        if not isinstance(plan, dict) or not plan:
            raise ValueError("approved plan is required")
        payload = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def request_plan_grant(self, *, user_id: str, session_id: str, identity_hash: str, plan_id: str,
                           plan_hash: str, plan_payload: str, risk_level: str, expires_at: str,
                           simulation_evidence: Optional[Dict[str, Any]] = None) -> str:
        """The sole factory for durable plan grants. Not wired to production yet."""
        grant_id = uuid.uuid4().hex
        self._grants.create_plan({
            "grant_id": grant_id, "user_id": user_id, "session_id": session_id,
            "identity_hash": identity_hash, "plan_id": plan_id, "plan_hash": plan_hash,
            "plan_payload": plan_payload, "risk_level": risk_level, "expires_at": expires_at,
            "simulation_evidence": simulation_evidence or {},
        })
        return grant_id

    def recover_approved_plan(self, grant_id: str) -> Dict[str, Any]:
        """Return only the exact persisted plan; tampering fails closed."""
        grant = self._grants.get_plan(grant_id)
        if not grant or grant["status"] not in ("approved", "in_progress"):
            raise PermissionError("approved plan grant is unavailable")
        payload = grant["plan_payload"]
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if digest != grant["plan_hash"]:
            raise PermissionError("approved plan hash mismatch")
        try:
            return json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PermissionError("approved plan payload is invalid") from exc

    def approve_plan_grant(self, grant_id: str, *, user_id: str) -> bool:
        return self._grants.transition_plan(grant_id, "pending", "approved", {"user_id": user_id})

    def issue_step_grant(self, grant: Dict[str, Any]) -> ExecutionGrantContext:
        """Derive one single-use step grant only from an approved/in-progress plan."""
        if not self._grants.create_step(grant):
            raise PermissionError("step grant cannot be derived from the approved plan")
        step = self._grants.get_step(grant["step_grant_id"])
        plan = self._grants.get_plan(grant["plan_grant_id"])
        if not step or not plan or not plan.get("approved_at"):
            raise PermissionError("durable grant context is incomplete")
        return ExecutionGrantContext(
            grant_id=step["step_grant_id"], plan_grant_id=step["plan_grant_id"],
            step_grant_id=step["step_grant_id"], user_id=plan["user_id"],
            session_id=step["session_id"], identity_hash=step["identity_hash"],
            plan_id=step["plan_id"], plan_hash=step["plan_hash"], step_id=step["step_id"],
            step_index=step["step_index"], tool_id=step["tool_id"], params_hash=step["params_hash"],
            approved_at=plan["approved_at"], expires_at=step["expires_at"],
        )

    def consume_step_grant(self, step_grant_id: str, binding: Dict[str, Any]) -> bool:
        return self._grants.consume_step(step_grant_id, binding)

    def resume_approved_plan(self, plan_grant_id: str, *, user_id: str, session_id: str, identity_hash: str) -> Dict[str, Any]:
        """Atomically claim a durable plan and return its immutable payload."""
        if not user_id or not session_id or not identity_hash:
            raise PermissionError("authenticated identity and session are required")
        plan = self._grants.get_plan(plan_grant_id)
        if not plan or plan["user_id"] != user_id or plan["session_id"] != session_id or plan["identity_hash"] != identity_hash:
            raise PermissionError("plan grant identity binding mismatch")
        if plan["status"] == "approved":
            if not self._grants.transition_plan(plan_grant_id, "approved", "in_progress", {
                "user_id": user_id, "session_id": session_id, "identity_hash": identity_hash,
            }):
                raise PermissionError("plan grant could not be resumed")
            plan = self._grants.get_plan(plan_grant_id)
        if not plan or plan["status"] != "in_progress":
            raise PermissionError("plan grant is not resumable")
        payload = self.recover_approved_plan(plan_grant_id)
        return {"plan": plan, "payload": payload}

    def issue_next_step_grant(
        self, *, plan_grant_id: str, user_id: str, session_id: str, identity_hash: str,
        step_id: str, step_index: int, tool_id: str, params: Dict[str, Any], expires_at: str,
    ) -> ExecutionGrantContext:
        """Issue only the next unconsumed step; never skip or duplicate authority."""
        plan = self._grants.get_plan(plan_grant_id)
        if not plan or plan["status"] != "in_progress":
            raise PermissionError("plan grant is not in progress")
        if any(plan[key] != value for key, value in {"user_id": user_id, "session_id": session_id, "identity_hash": identity_hash}.items()):
            raise PermissionError("plan grant identity binding mismatch")
        for index in range(step_index):
            previous = self._grants._db.fetchone(
                "SELECT status FROM step_execution_grants WHERE plan_grant_id=? AND step_index=?", (plan_grant_id, index)
            )
            if not previous or previous["status"] != "consumed":
                raise PermissionError("step order violation")
        existing = self._grants._db.fetchone(
            "SELECT * FROM step_execution_grants WHERE plan_grant_id=? AND step_index=?", (plan_grant_id, step_index)
        )
        if existing:
            if existing["status"] != "approved":
                raise PermissionError("step grant already consumed or failed")
            return ExecutionGrantContext(
                grant_id=existing["step_grant_id"], plan_grant_id=plan_grant_id, step_grant_id=existing["step_grant_id"],
                user_id=user_id, session_id=session_id, identity_hash=identity_hash, plan_id=plan["plan_id"],
                plan_hash=plan["plan_hash"], step_id=existing["step_id"], step_index=step_index,
                tool_id=existing["tool_id"], params_hash=existing["params_hash"], approved_at=plan["approved_at"], expires_at=existing["expires_at"],
            )
        params_hash = self.canonical_params_hash(tool_id=tool_id, params=params, plan_id=plan["plan_id"], identity_hash=identity_hash)
        step_grant_id = uuid.uuid4().hex
        return self.issue_step_grant({
            "step_grant_id": step_grant_id, "plan_grant_id": plan_grant_id, "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"], "step_id": step_id, "step_index": step_index, "tool_id": tool_id,
            "params_hash": params_hash, "identity_hash": identity_hash, "session_id": session_id, "expires_at": expires_at,
        })

    def complete_plan(self, plan_grant_id: str, *, user_id: str, session_id: str, identity_hash: str) -> bool:
        plan = self._grants.get_plan(plan_grant_id)
        if not plan or any(plan[key] != value for key, value in {"user_id": user_id, "session_id": session_id, "identity_hash": identity_hash}.items()):
            return False
        try:
            expected_steps = len(json.loads(plan["plan_payload"]).get("steps", []))
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        consumed = self._grants._db.fetchone(
            "SELECT COUNT(*) AS count FROM step_execution_grants WHERE plan_grant_id=? AND status='consumed'", (plan_grant_id,)
        )
        if not expected_steps or not consumed or consumed["count"] != expected_steps:
            return False
        return self._grants.transition_plan(plan_grant_id, "in_progress", "consumed", {"user_id": user_id, "session_id": session_id, "identity_hash": identity_hash})

    def fail_plan(self, plan_grant_id: str, *, user_id: str, session_id: str, identity_hash: str) -> bool:
        """Durably close a failed approved plan without authorizing retries."""
        plan = self._grants.get_plan(plan_grant_id)
        if not plan or any(
            plan[key] != value
            for key, value in {
                "user_id": user_id,
                "session_id": session_id,
                "identity_hash": identity_hash,
            }.items()
        ):
            return False
        return self._grants.transition_plan(
            plan_grant_id,
            "in_progress",
            "failed",
            {"user_id": user_id, "session_id": session_id, "identity_hash": identity_hash},
        )

    @staticmethod
    def _redact_context(context: Dict[str, Any]) -> Dict[str, Any]:
        safe = {}
        for key, value in context.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in _SECRET_KEYS):
                safe[key] = "<REDACTED>"
            elif isinstance(value, dict):
                safe[key] = ConfirmationBroker._redact_context(value)
            elif isinstance(value, str):
                safe[key] = ConfirmationBroker._redact(value)
            else:
                safe[key] = value
        return safe

    @staticmethod
    def _redact(value: str) -> str:
        result = str(value)
        for pattern in _SECRET_KEYS:
            marker_lower = pattern.replace("_", "").replace("-", "")
            result_lower = result.lower().replace("_", "").replace("-", "")
            if marker_lower in result_lower:
                return "<REDACTED>"
        return result

    def request(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        reason: str,
        risk_level: str = "unknown",
        plan_id: str = "",
    ) -> str:
        identity = context.get("identity") or {}
        user_id = identity.get("user_id")
        session_id = identity.get("session_id") or context.get("session_id")
        if not user_id:
            raise ValueError("Authenticated user is required for confirmation")
        action_id = uuid.uuid4().hex

        params_redacted = self._redact_context({"p": params}).get("p", params)
        params_hash = self._hash(params_redacted)

        safe_context = {
            "identity": {
                "user_id": user_id,
                "role": identity.get("role"),
                "session_id": session_id or "",
            },
            "execution_id": context.get("execution_id"),
        }
        # Bind the approval to the authenticated session as well as the user.
        # A user id alone is insufficient: it would allow a stolen action id to
        # be replayed from a different session of the same account.
        identity_hash = self._hash({"user_id": user_id, "session_id": identity.get("session_id", "")})

        self._memory.store_pending_action(
            PendingActionRecord(
                action_id=action_id,
                tool_id=tool_id,
                params={
                    "kind": "tool_confirmation",
                    "tool_id": tool_id,
                    "params": dict(params_redacted),
                    "context": safe_context,
                    "user_id": user_id,
                },
                reason=reason,
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                ttl_seconds=self._ttl_seconds,
                risk_level=risk_level,
                plan_id=plan_id,
                params_hash=params_hash,
                identity_hash=identity_hash,
                redacted=True,
            )
        )
        return action_id

    def consume(
        self, action_id: str, user_id: str, approved: bool, *, session_id: Optional[str] = None
    ) -> Optional[ConfirmationGrant]:
        # Single-use consumption is atomic: the backend removes the record in
        # one lock-protected / transactional step (SELECT + DELETE).  A
        # mismatched approver cannot consume another user's confirmation and
        # concurrent approvals cannot both obtain a grant, because only the
        # thread that atomically removed the record receives it back.
        pre = self._memory.get_pending_action(action_id)
        if pre is None or pre.params.get("kind") != "tool_confirmation":
            return None

        record = self._memory.consume_pending_action(action_id, expected_user_id=user_id)
        if record is None or record.params.get("kind") != "tool_confirmation":
            return None

        if approved:
            stored_params = dict(record.params["params"])
            stored_hash = self._hash(stored_params)
            if record.params_hash and stored_hash != record.params_hash:
                raise PermissionError("Params hash mismatch — approval tampered with")
            if record.identity_hash:
                stored_session_id = (record.params.get("context", {}).get("identity", {}) or {}).get("session_id", "")
                # Callers that do not carry session information retain legacy
                # compatibility.  The API always supplies it and therefore
                # receives the stronger session-bound replay protection.
                effective_session_id = stored_session_id if session_id is None else session_id
                current_identity_hash = self._hash({
                    "user_id": user_id,
                    "session_id": effective_session_id,
                })
                if record.identity_hash != current_identity_hash:
                    raise PermissionError("Identity hash mismatch — replay detected")

        created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - created).total_seconds() > record.ttl_seconds:
            return None

        if not approved:
            return None

        return ConfirmationGrant(
            action_id=action_id,
            tool_id=record.params["tool_id"],
            params=dict(record.params["params"]),
            context=dict(record.params.get("context") or {}),
            user_id=user_id,
            risk_level=record.risk_level,
            plan_id=record.plan_id,
            params_hash=record.params_hash,
            identity_hash=record.identity_hash,
        )

    def peek(self, action_id: str) -> Optional[Dict[str, Any]]:
        record = self._memory.get_pending_action(action_id)
        if record is None or record.params.get("kind") != "tool_confirmation":
            return None
        return {
            "action_id": record.action_id,
            "tool_id": record.tool_id,
            "reason": record.reason,
            "risk_level": record.risk_level,
            "plan_id": record.plan_id,
            "created_at": record.created_at,
            "ttl_seconds": record.ttl_seconds,
            "redacted": record.redacted,
        }
