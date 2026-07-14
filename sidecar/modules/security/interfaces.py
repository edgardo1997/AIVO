import warnings
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuthContext:
    """Deprecated: use IdentityContext from modules.auth instead."""
    user_id: str = "local"
    client_id: str = "unknown"
    session_id: str = ""

    def __post_init__(self):
        warnings.warn(
            "AuthContext is deprecated, use IdentityContext from modules.auth",
            DeprecationWarning, stacklevel=3,
        )


@dataclass
class ValidationResult:
    allowed: bool
    reason: str
    risk_level: str
    normalized_path: str


class PathSecurityError(Exception):
    def __init__(self, reason: str, path: str = "", risk_level: str = "unknown"):
        self.reason = reason
        self.path = path
        self.risk_level = risk_level
        super().__init__(f"[{risk_level}] {reason}: {path}" if path else reason)
