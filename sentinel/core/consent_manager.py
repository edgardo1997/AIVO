import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class ConsentType(str, Enum):
    ONCE = "once"
    SESSION = "session"
    PERMANENT = "permanent"


@dataclass
class ConsentGrant:
    id: str
    user_id: str
    tool_id: str
    consent_type: ConsentType
    granted_at: float
    expires_at: Optional[float]
    risk_level: str
    params_pattern: Optional[Dict[str, Any]] = None
    revoked: bool = False
    label: str = ""

    def is_valid(self, current_time: Optional[float] = None) -> bool:
        if self.revoked:
            return False
        if self.consent_type == ConsentType.ONCE:
            return False
        if self.expires_at is not None:
            now = current_time or time.time()
            if now > self.expires_at:
                return False
        return True

    def matches(self, tool_id: str, params: Optional[Dict[str, Any]] = None) -> bool:
        if self.tool_id != tool_id:
            return False
        if self.params_pattern and params:
            for key, value in self.params_pattern.items():
                if key not in params or params[key] != value:
                    return False
        return True


@dataclass
class PendingConsent:
    id: str
    user_id: str
    tool_id: str
    params: Dict[str, Any]
    risk_level: str
    risk_label: str
    risk_description: str
    is_read_only: bool
    is_reversible: bool
    affected_resources: List[str]
    estimated_impact: str
    simulation_summary: str
    plan_data: Dict[str, Any]
    intent_data: Dict[str, Any]
    context_summary: Dict[str, Any]
    created_at: float
    expires_at: float
    can_grant_permanent: bool = True


class ConsentManager:
    def __init__(self, storage=None):
        self._storage = storage or _InMemoryConsentStorage()
        self._pending: Dict[str, PendingConsent] = {}

    def request_consent(
        self,
        user_id: str,
        tool_id: str,
        params: Dict[str, Any],
        risk_level: str,
        risk_label: str,
        risk_description: str,
        is_read_only: bool,
        is_reversible: bool,
        affected_resources: List[str],
        estimated_impact: str,
        simulation_summary: str,
        plan_data: Dict[str, Any],
        intent_data: Dict[str, Any],
        context_summary: Dict[str, Any],
        ttl: float = 600.0,
    ) -> PendingConsent:
        now = time.time()
        pending = PendingConsent(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tool_id=tool_id,
            params=params,
            risk_level=risk_level,
            risk_label=risk_label,
            risk_description=risk_description,
            is_read_only=is_read_only,
            is_reversible=is_reversible,
            affected_resources=affected_resources,
            estimated_impact=estimated_impact,
            simulation_summary=simulation_summary,
            plan_data=plan_data,
            intent_data=intent_data,
            context_summary=context_summary,
            created_at=now,
            expires_at=now + ttl,
            can_grant_permanent=is_reversible,
        )
        self._pending[pending.id] = pending
        return pending

    def check_consent(
        self,
        user_id: str,
        tool_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[ConsentGrant]:
        grants = self._storage.list_active(user_id)
        for grant in grants:
            if grant.matches(tool_id, params) and grant.is_valid():
                if grant.consent_type == ConsentType.ONCE:
                    self._storage.remove(grant.id)
                return grant
        return None

    def grant_consent(
        self,
        pending_id: str,
        user_id: str,
        consent_type: ConsentType,
        session_id: Optional[str] = None,
        ttl: Optional[float] = None,
    ) -> Optional[ConsentGrant]:
        pending = self._pending.get(pending_id)
        if not pending:
            return None
        if pending.user_id != user_id:
            return None
        if time.time() > pending.expires_at:
            del self._pending[pending_id]
            return None

        now = time.time()
        expires_at = None
        if consent_type == ConsentType.SESSION:
            expires_at = now + (ttl or 86400.0)
        elif consent_type == ConsentType.ONCE:
            expires_at = None

        grant = ConsentGrant(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tool_id=pending.tool_id,
            consent_type=consent_type,
            granted_at=now,
            expires_at=expires_at,
            risk_level=pending.risk_level,
            params_pattern=pending.params if consent_type != ConsentType.PERMANENT else None,
            label=f"{pending.risk_label}: {pending.tool_id}",
        )

        if consent_type != ConsentType.ONCE:
            self._storage.save(grant)

        del self._pending[pending_id]
        return grant

    def _direct_grant(
        self,
        grant_id: str,
        user_id: str,
        tool_id: str,
        consent_type: ConsentType,
        risk_level: str = "medium",
        risk_label: str = "",
        session_id: Optional[str] = None,
        ttl: Optional[float] = None,
    ) -> ConsentGrant:
        now = time.time()
        expires_at = None
        if consent_type == ConsentType.SESSION:
            expires_at = now + (ttl or 86400.0)
        grant = ConsentGrant(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tool_id=tool_id,
            consent_type=consent_type,
            granted_at=now,
            expires_at=expires_at,
            risk_level=risk_level,
            label=risk_label or f"Manual approval: {tool_id}",
        )
        if consent_type != ConsentType.ONCE:
            self._storage.save(grant)
        return grant

    def revoke_consent(self, grant_id: str, user_id: str) -> bool:
        grant = self._storage.get(grant_id)
        if not grant:
            return False
        if grant.user_id != user_id:
            return False
        grant.revoked = True
        self._storage.save(grant)
        return True

    def list_grants(self, user_id: str) -> List[ConsentGrant]:
        return [g for g in self._storage.list_active(user_id) if g.is_valid()]

    def list_pending(self, user_id: str) -> List[PendingConsent]:
        now = time.time()
        return [p for p in self._pending.values() if p.user_id == user_id and p.expires_at > now]

    def get_pending(self, pending_id: str) -> Optional[PendingConsent]:
        pending = self._pending.get(pending_id)
        if not pending:
            return None
        if time.time() > pending.expires_at:
            del self._pending[pending_id]
            return None
        return pending

    def revoke_all(self, user_id: str) -> int:
        grants = self._storage.list_active(user_id)
        count = 0
        for grant in grants:
            if grant.user_id == user_id:
                grant.revoked = True
                self._storage.save(grant)
                count += 1
        return count

    def cleanup_expired(self) -> int:
        now = time.time()
        expired_pending = [pid for pid, p in self._pending.items() if p.expires_at <= now]
        for pid in expired_pending:
            del self._pending[pid]
        return self._storage.cleanup(now)


class ConsentStorage:
    def save(self, grant: ConsentGrant) -> None: ...
    def get(self, grant_id: str) -> Optional[ConsentGrant]: ...
    def remove(self, grant_id: str) -> bool: ...
    def list_active(self, user_id: str) -> List[ConsentGrant]: ...
    def cleanup(self, before: float) -> int: ...


class _InMemoryConsentStorage(ConsentStorage):
    def __init__(self):
        self._grants: Dict[str, ConsentGrant] = {}

    def save(self, grant: ConsentGrant) -> None:
        self._grants[grant.id] = grant

    def get(self, grant_id: str) -> Optional[ConsentGrant]:
        return self._grants.get(grant_id)

    def remove(self, grant_id: str) -> bool:
        return self._grants.pop(grant_id, None) is not None

    def list_active(self, user_id: str) -> List[ConsentGrant]:
        return [g for g in self._grants.values() if g.user_id == user_id]

    def cleanup(self, before: float) -> int:
        count = 0
        expired = [gid for gid, g in self._grants.items() if g.expires_at is not None and g.expires_at <= before]
        for gid in expired:
            del self._grants[gid]
            count += 1
        return count
