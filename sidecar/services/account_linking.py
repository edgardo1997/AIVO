"""Secure account linking between local profiles and external identity providers.

The canonical external identity is `issuer + subject`. Email is never used as
a primary key and never causes automatic account takeover.
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from repositories.engine import get_session
from repositories.models import UserProfile, UserPreferenceV2

logger = logging.getLogger("sentinel.account_linking")


class IdentityLink:
    def __init__(
        self,
        user_id: str,
        provider: str,
        issuer: str,
        subject: str,
        email: str,
        verified_email: bool,
        display_name: str,
        created_at: str,
    ):
        self.user_id = user_id
        self.provider = provider
        self.issuer = issuer
        self.subject = subject
        self.email = email
        self.verified_email = verified_email
        self.display_name = display_name
        self.created_at = created_at

    def to_dict(self):
        return {
            "provider": self.provider,
            "issuer": self.issuer,
            "subject": self.subject,
            "email": self.email,
            "verified_email": self.verified_email,
            "display_name": self.display_name,
            "created_at": self.created_at,
        }


class AccountLinkingService:
    """Service to link, unlink and resolve external identities.

    Rules:
    - issuer+subject exists → login as the linked local account.
    - same verified email but different issuer → never auto-link.
    - unverified email → cannot link.
    - local profile must be authenticated before linking.
    - unlinking does not delete the local profile.
    """

    _PREF_PREFIX = "linked_identity_"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _key(self, provider: str, issuer: str, subject: str) -> str:
        return f"{self._PREF_PREFIX}{provider}:{issuer}:{subject}"

    def _session(self) -> Session:
        return get_session()

    def _get_pref(self, session: Session, user_id: str, key: str) -> Optional[str]:
        row = session.execute(
            select(UserPreferenceV2).where(
                UserPreferenceV2.user_id == user_id,
                UserPreferenceV2.key == key,
            )
        ).scalar_one_or_none()
        return row.value if row else None

    def _set_pref(self, session: Session, user_id: str, key: str, value: str):
        now = self._now()
        row = session.execute(
            select(UserPreferenceV2).where(
                UserPreferenceV2.user_id == user_id,
                UserPreferenceV2.key == key,
            )
        ).scalar_one_or_none()
        if row:
            row.value = value
            row.updated_at = now
        else:
            session.add(UserPreferenceV2(user_id=user_id, key=key, value=value, updated_at=now))

    def _audit(self, user_id: str, action: str, detail: str):
        # TODO: add formal audit_log entry; for now log at INFO.
        logger.info("Account linking audit: user=%s action=%s detail=%s", user_id, action, detail)

    def find_identity(self, provider: str, issuer: str, subject: str) -> Optional[IdentityLink]:
        key = self._key(provider, issuer, subject)
        with self._session() as session:
            rows = session.execute(
                select(UserPreferenceV2.user_id, UserPreferenceV2.value)
                .where(UserPreferenceV2.key == key)
            ).fetchall()
            if not rows:
                return None
            user_id, raw = rows[0]
            parts = raw.split("\n")
            if len(parts) < 6:
                return None
            return IdentityLink(
                user_id=user_id,
                provider=provider,
                issuer=issuer,
                subject=subject,
                email=parts[0],
                verified_email=parts[1] == "1",
                display_name=parts[2],
                created_at=parts[5],
            )

    def find_by_email(self, email: str) -> list[IdentityLink]:
        """Return linked identities with the same email, but only for same issuer if any."""
        results = []
        with self._session() as session:
            rows = session.execute(
                select(UserPreferenceV2.user_id, UserPreferenceV2.key, UserPreferenceV2.value)
                .where(UserPreferenceV2.key.like(f"{self._PREF_PREFIX}%"))
            ).fetchall()
            for user_id, key, raw in rows:
                parts = raw.split("\n")
                if len(parts) < 6:
                    continue
                if parts[0] == email:
                    provider, issuer, subject = key.replace(self._PREF_PREFIX, "", 1).split(":", 2)
                    results.append(IdentityLink(
                        user_id=user_id,
                        provider=provider,
                        issuer=issuer,
                        subject=subject,
                        email=parts[0],
                        verified_email=parts[1] == "1",
                        display_name=parts[2],
                        created_at=parts[5],
                    ))
        return results

    def validate_link_request(
        self,
        local_user_id: str,
        provider: str,
        issuer: str,
        subject: str,
        email: str,
        verified_email: bool,
    ) -> tuple[bool, str]:
        if not local_user_id:
            return False, "Local profile must be authenticated"
        if not verified_email:
            return False, "Unverified email cannot link"

        existing = self.find_identity(provider, issuer, subject)
        if existing and existing.user_id != local_user_id:
            return False, "This external identity is already linked to another account"
        if existing and existing.user_id == local_user_id:
            return True, ""

        # Same email with different issuer must not auto-link or allow takeover.
        for link in self.find_by_email(email):
            if link.issuer != issuer or link.subject != subject or link.user_id != local_user_id:
                return False, "Email already linked to a different provider; manual linking not allowed"

        return True, ""

    def link_identity(
        self,
        local_user_id: str,
        provider: str,
        issuer: str,
        subject: str,
        email: str,
        verified_email: bool,
        display_name: str,
    ) -> IdentityLink:
        valid, reason = self.validate_link_request(
            local_user_id, provider, issuer, subject, email, verified_email
        )
        if not valid:
            self._audit(local_user_id, "link_rejected", reason)
            raise ValueError(reason)

        with self._session() as session:
            key = self._key(provider, issuer, subject)
            now = self._now()
            value = "\n".join([
                email,
                "1" if verified_email else "0",
                display_name,
                local_user_id,
                secrets.token_urlsafe(16),
                now,
            ])
            self._set_pref(session, local_user_id, key, value)
            session.commit()
            self._audit(local_user_id, "linked", f"{provider} {issuer}/{subject}")
            return IdentityLink(
                user_id=local_user_id,
                provider=provider,
                issuer=issuer,
                subject=subject,
                email=email,
                verified_email=verified_email,
                display_name=display_name,
                created_at=now,
            )

    def unlink_identity(self, local_user_id: str, provider: str, issuer: str, subject: str) -> bool:
        with self._session() as session:
            key = self._key(provider, issuer, subject)
            row = session.execute(
                select(UserPreferenceV2).where(
                    UserPreferenceV2.user_id == local_user_id,
                    UserPreferenceV2.key == key,
                )
            ).scalar_one_or_none()
            if not row:
                return False
            session.delete(row)
            session.commit()
            self._audit(local_user_id, "unlinked", f"{provider} {issuer}/{subject}")
            return True

    def list_linked_identities(self, local_user_id: str) -> list[IdentityLink]:
        with self._session() as session:
            rows = session.execute(
                select(UserPreferenceV2.key, UserPreferenceV2.value)
                .where(
                    UserPreferenceV2.user_id == local_user_id,
                    UserPreferenceV2.key.like(f"{self._PREF_PREFIX}%"),
                )
            ).fetchall()
            results = []
            for key, raw in rows:
                parts = raw.split("\n")
                if len(parts) < 6:
                    continue
                provider, issuer, subject = key.replace(self._PREF_PREFIX, "", 1).split(":", 2)
                results.append(IdentityLink(
                    user_id=local_user_id,
                    provider=provider,
                    issuer=issuer,
                    subject=subject,
                    email=parts[0],
                    verified_email=parts[1] == "1",
                    display_name=parts[2],
                    created_at=parts[5],
                ))
            return results
