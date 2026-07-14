import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from repositories.audit_repository import AuditRepository
from sentinel.policies.output_policies import SENSITIVE_PATTERNS

log = logging.getLogger("sentinel.audit_service")

PIPELINE_STEPS = ["identity", "intent", "decision", "policy", "execution", "quality"]


class AuditService:
    def __init__(self, repo: AuditRepository = None):
        self.repo = repo or AuditRepository()

    def set_repo(self, repo: AuditRepository):
        self.repo = repo

    def log_action(self, action: str, details: str, status: str = "info", user: str = "local"):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "action": action,
            "details": self._redact(details),
            "status": status,
            "user": user,
        }
        self.repo.append(self._sanitize(entry))

    def log_pipeline(
        self,
        execution_id: str,
        *,
        identity: Optional[dict] = None,
        intent: Optional[dict] = None,
        decision: Optional[dict] = None,
        policy: Optional[dict] = None,
        execution: Optional[dict] = None,
        quality: Optional[dict] = None,
        tool_id: str = "",
        error: Optional[str] = None,
    ) -> None:
        pipeline = {
            "identity": identity,
            "intent": intent,
            "decision": decision,
            "policy": policy,
            "execution": execution,
            "quality": quality,
        }
        status = "error" if error else "success"
        actor = (identity or {}).get("user_id", "unknown")
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "action": f"pipeline.{tool_id}" if tool_id else "pipeline",
            "execution_id": execution_id,
            "details": json.dumps({"execution_id": execution_id, "tool_id": tool_id}),
            "status": status,
            "user": actor,
            "payload": {
                "execution_id": execution_id,
                "tool_id": tool_id,
                "pipeline": pipeline,
                "error": error,
            },
        }
        self.repo.append(self._sanitize(entry))

    def log_gateway_authorization(
        self,
        execution_id: str,
        *,
        identity: dict,
        decision: Optional[dict],
        policy: Optional[dict],
        tool_id: str,
        params: dict,
    ) -> None:
        actor = identity.get("user_id", "unknown")
        self.repo.append(self._sanitize({
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "action": f"pipeline.preflight.{tool_id}",
            "execution_id": execution_id,
            "details": json.dumps({"execution_id": execution_id, "tool_id": tool_id}),
            "status": "authorized",
            "user": actor,
            "payload": {
                "execution_id": execution_id,
                "tool_id": tool_id,
                "pipeline": {
                    "identity": identity,
                    "intent": None,
                    "decision": decision,
                    "policy": policy,
                    "execution": {"phase": "preflight", "params_present": sorted(params)},
                    "quality": None,
                },
                "error": None,
            },
        }))

    @classmethod
    def _redact(cls, value: str) -> str:
        result = str(value)
        for pattern in SENSITIVE_PATTERNS:
            result = pattern.sub("<REDACTED>", result)
        return result

    @classmethod
    def _sanitize(cls, value):
        if isinstance(value, str):
            return cls._redact(value)
        if isinstance(value, dict):
            sanitized = {}
            for key, item in value.items():
                normalized = str(key).lower().replace("-", "_")
                if any(marker in normalized for marker in ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization")):
                    sanitized[key] = "<REDACTED>"
                else:
                    sanitized[key] = cls._sanitize(item)
            return sanitized
        if isinstance(value, list):
            return [cls._sanitize(item) for item in value]
        return value

    def get_log(self, limit: int = None, action_filter: str = None) -> dict:
        entries = self.repo.read_all(limit, action_filter)
        total = self.repo.count()
        return {"entries": entries, "total": total}

    def verify_integrity(self) -> dict:
        return self.repo.verify_integrity()
