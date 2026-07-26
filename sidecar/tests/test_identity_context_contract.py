from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sentinel.contracts import IdentityContextV1


def test_same_identity_context_produces_same_hash():
    created = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    first = IdentityContextV1.create(
        user_id="user_x",
        session_id="session_x",
        roles=["Admin", "user"],
        authentication_method="LOCAL",
        created_at=created,
    )
    second = IdentityContextV1.create(
        user_id="user_x",
        session_id="session_x",
        roles=["user", "admin"],
        authentication_method="local",
        created_at=created,
    )
    assert first.identity_hash == second.identity_hash
    assert first.roles == ("admin", "user")


def test_session_change_changes_identity_hash():
    created = datetime.now(timezone.utc)
    base = dict(
        user_id="user_x",
        roles=["user"],
        authentication_method="local",
        created_at=created,
    )
    assert (
        IdentityContextV1.create(session_id="one", **base).identity_hash
        != IdentityContextV1.create(session_id="two", **base).identity_hash
    )


def test_invalid_identity_context_is_rejected():
    with pytest.raises(ValidationError, match="at least 1 item"):
        IdentityContextV1.create(
            user_id="user_x",
            session_id="session_x",
            roles=[],
            authentication_method="local",
            created_at=datetime.now(timezone.utc),
        )
    valid = IdentityContextV1.create(
        user_id="user_x",
        session_id="session_x",
        roles=["user"],
        authentication_method="local",
        created_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValidationError, match="canonical identity"):
        IdentityContextV1.model_validate({**valid.model_dump(), "identity_hash": "f" * 64})
