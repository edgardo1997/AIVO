"""Pure adapter from PendingActionRecord to a non-authoritative consent record."""

import hashlib
import json
from datetime import datetime, timedelta

from sentinel.contracts import PendingConsentStatusV1, PendingConsentV1
from sentinel.core.operational_memory import PendingActionRecord

from ._ids import require_id


def _created_at(record: PendingActionRecord) -> datetime:
    try:
        value = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("PendingActionRecord.created_at must be a valid ISO timestamp") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("PendingActionRecord.created_at must include timezone information")
    return value


def _params_hash(params: dict) -> str:
    canonical = json.dumps(
        params,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def pending_action_to_v1(
    record: PendingActionRecord,
    *,
    intent_id: str,
    step_id: str,
    user_id: str,
    status: PendingConsentStatusV1 = PendingConsentStatusV1.PENDING,
) -> PendingConsentV1:
    """Convert pending state only; this function cannot create a grant."""
    if not isinstance(record, PendingActionRecord):
        raise TypeError("record must be a PendingActionRecord")
    created_at = _created_at(record)
    return PendingConsentV1(
        schema_version="1.0",
        pending_consent_id=record.action_id,
        intent_id=require_id(intent_id, "intent_id"),
        plan_id=require_id(record.plan_id, "plan_id"),
        step_id=require_id(step_id, "step_id"),
        tool_id=record.tool_id,
        user_id=require_id(user_id, "user_id"),
        risk_level=record.risk_level,
        params_hash=_params_hash(record.params),
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=record.ttl_seconds),
        status=status,
    )
