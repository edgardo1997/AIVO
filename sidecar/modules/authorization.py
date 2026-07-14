import logging

from fastapi import Depends, HTTPException, Request

from .auth import IdentityContext

logger = logging.getLogger("sentinel.authorization")

LEVEL_RANK = {
    "admin": 4,
    "user": 3,
    "auto": 2,
    "confirm": 2,
    "viewer": 1,
    "view": 1,
}


def require_level(minimum: str):
    def _check(request: Request) -> IdentityContext:
        identity: IdentityContext = getattr(request.state, "identity", None)
        if identity is None or not identity.is_authenticated:
            raise HTTPException(status_code=401, detail="Authentication required")
        identity_rank = LEVEL_RANK.get(identity.level, 0)
        required_rank = LEVEL_RANK.get(minimum, 0)
        if identity_rank < required_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Requires level '{minimum}', identity has level '{identity.level}'",
            )
        return identity

    return _check


require_admin = Depends(require_level("admin"))
require_confirm = Depends(require_level("confirm"))
require_view = Depends(require_level("view"))


def check_level(identity: IdentityContext, minimum: str) -> None:
    identity_rank = LEVEL_RANK.get(identity.level, 0)
    required_rank = LEVEL_RANK.get(minimum, 0)
    if identity_rank < required_rank:
        raise PermissionError(f"Requires level '{minimum}', identity has level '{identity.level}'")
