"""Pure grant expiration checks."""

from datetime import datetime

from sentinel.contracts import AuthorizationGrantV1


def grant_is_expired(grant: AuthorizationGrantV1, *, now: datetime) -> bool:
    return now >= grant.expires_at
