"""Canonical security level definitions for Sentinel.

Single source of truth for LEVEL_RANK and role→level mappings.
All modules MUST import from here instead of defining their own."""

LEVEL_RANK = {
    "admin": 4,
    "confirm": 3,
    "auto": 2,
    "view": 1,
}

ROLE_TO_LEVEL = {
    "admin": "admin",
    "user": "confirm",
    "viewer": "view",
    "service": "auto",
}


def require_level(identity_level: str, minimum: str) -> bool:
    """Check if identity_level meets or exceeds minimum."""
    if identity_level not in LEVEL_RANK:
        return False
    if minimum not in LEVEL_RANK:
        return False
    return LEVEL_RANK[identity_level] >= LEVEL_RANK[minimum]
