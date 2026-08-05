"""Tests for secure account linking."""

import pytest

from repositories.local_profile_repository import LocalProfileRepository
from services.account_linking import AccountLinkingService


@pytest.fixture
def local():
    repo = LocalProfileRepository()
    p = repo.create("Edgardo")
    return p["user_id"]


@pytest.fixture
def service():
    from repositories.engine import get_session
    from repositories.models import UserPreferenceV2
    from sqlalchemy import delete
    s = AccountLinkingService()
    with get_session() as session:
        session.execute(delete(UserPreferenceV2).where(UserPreferenceV2.key.like("linked_identity_%")))
        session.commit()
    return s


class TestAccountLinking:
    def _email(self, local):
        return f"{local}@example.com"

    def test_same_issuer_subject_resolves_same_account(self, service, local):
        service.link_identity(local, "google", "https://accounts.google.com", "sub123", self._email(local), True, "Edgar")
        found = service.find_identity("google", "https://accounts.google.com", "sub123")
        assert found is not None
        assert found.user_id == local

    def test_same_email_different_issuer_does_not_auto_link(self, service, local):
        service.link_identity(local, "google", "https://accounts.google.com", "sub123", self._email(local), True, "Edgar")
        with pytest.raises(ValueError):
            service.link_identity(local, "microsoft", "https://login.microsoftonline.com/common/v2.0", "sub456", self._email(local), True, "Edgar")

    def test_unverified_email_cannot_link(self, service, local):
        with pytest.raises(ValueError):
            service.link_identity(local, "google", "https://accounts.google.com", "sub789", self._email(local), False, "Edgar")

    def test_link_requires_local_profile(self, service):
        with pytest.raises(ValueError):
            service.link_identity("", "google", "https://accounts.google.com", "sub123", "none@example.com", True, "Edgar")

    def test_link_is_idempotent(self, service, local):
        a = service.link_identity(local, "google", "https://accounts.google.com", "sub123", self._email(local), True, "Edgar")
        b = service.link_identity(local, "google", "https://accounts.google.com", "sub123", self._email(local), True, "Edgar")
        assert a.user_id == b.user_id

    def test_conflicting_identity_rejected(self, service, local):
        service.link_identity(local, "google", "https://accounts.google.com", "sub123", self._email(local), True, "Edgar")
        other_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(ValueError):
            service.link_identity(other_id, "google", "https://accounts.google.com", "sub123", self._email(local), True, "Edgar")

    def test_unlink_preserves_local_profile(self, service, local):
        service.link_identity(local, "google", "https://accounts.google.com", "sub123", self._email(local), True, "Edgar")
        assert service.unlink_identity(local, "google", "https://accounts.google.com", "sub123")
        repo = LocalProfileRepository()
        p = repo.get(local)
        assert p is not None
        assert p["user_id"] == local
