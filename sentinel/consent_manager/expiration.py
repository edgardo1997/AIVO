"""Pure expiration checks; no scheduler or background work."""

from datetime import datetime

from sentinel.contracts import ConsentDecisionResultV1


def is_expired(
    consent: ConsentDecisionResultV1,
    *,
    now: datetime,
) -> bool:
    return now >= consent.expiration_time
