import logging
import os
import re
from typing import Any, Optional

import warnings
from .interfaces import AuthContext, PathSecurityError, ValidationResult
from .path_policy import (
    is_sensitive_filename,
    path_is_within_allowed,
    path_matches_blocked,
    get_blocked_paths,
)

log = logging.getLogger("sentinel.path_guardian")


def _unwrap_identity(context) -> Optional[dict]:
    if context is None:
        return None
    if isinstance(context, AuthContext):
        warnings.warn(
            "AuthContext passed to PathGuardian is deprecated, use IdentityContext",
            DeprecationWarning,
            stacklevel=4,
        )
        return {"user_id": context.user_id, "client_id": context.client_id, "level": "confirm"}
    if hasattr(context, "user_id") and hasattr(context, "level"):
        client_id = getattr(context, "client_id", getattr(context, "user_id", ""))
        return {"user_id": context.user_id, "client_id": client_id, "level": context.level}
    if isinstance(context, dict):
        return context
    return None


class PathGuardian:
    def __init__(self):
        self._max_path_length = 260

    def validate_read(self, path: str, context: Optional[Any] = None) -> ValidationResult:
        return self._validate(path, "read", _unwrap_identity(context))

    def validate_write(self, path: str, context: Optional[Any] = None) -> ValidationResult:
        return self._validate(path, "write", _unwrap_identity(context))

    def validate_delete(self, path: str, context: Optional[Any] = None) -> ValidationResult:
        return self._validate(path, "delete", _unwrap_identity(context))

    def validate_search(self, root: str, context: Optional[Any] = None) -> ValidationResult:
        if not root or not root.strip():
            return self._deny("Search root path is empty", "medium")
        normalized = self._normalize(root)
        blocked, blocked_by = path_matches_blocked(normalized)
        if blocked:
            return self._deny(f"Search root blocked: matches '{blocked_by}'", "critical", normalized)
        return self._allow(normalized)

    def resolve_path(self, path: str) -> str:
        result = self._validate(path, "resolve", None)
        if not result.allowed:
            raise PathSecurityError(result.reason, path, result.risk_level)
        return result.normalized_path

    def _validate(self, path: str, operation: str, context: Optional[dict] = None) -> ValidationResult:
        if not path or not path.strip():
            return self._deny("Path is empty", "medium")

        if len(path) > self._max_path_length:
            return self._deny(f"Path exceeds max length ({len(path)} > {self._max_path_length})", "medium")

        if self._has_traversal(path):
            return self._deny("Path traversal detected", "high", self._normalize(path))

        normalized = self._normalize(path)

        sensitive_reason = self._check_sensitive(normalized)
        if sensitive_reason:
            return self._deny(sensitive_reason, "critical", normalized)

        blocked, blocked_by = path_matches_blocked(normalized)
        if blocked:
            return self._deny(f"Path is blocked: matches '{blocked_by}'", "critical", normalized)

        real_path = self._resolve_symlink(normalized)
        if real_path != normalized:
            blocked_real, blocked_by_real = path_matches_blocked(real_path)
            if blocked_real:
                return self._deny(
                    f"Symlink target blocked: '{real_path}' matches '{blocked_by_real}'",
                    "critical",
                    normalized,
                )

        if operation in ("write", "delete"):
            allowed, _ = path_is_within_allowed(normalized)
            if not allowed:
                if real_path != normalized:
                    allowed, _ = path_is_within_allowed(real_path)
                if not allowed:
                    return self._deny(f"Path outside allowed directories for {operation}", "high", normalized)

        if not os.path.exists(normalized) and operation not in ("write", "resolve"):
            return self._deny(f"Path does not exist: {normalized}", "low", normalized)

        risk = self._assess_risk(operation, normalized)
        return self._allow(normalized, risk)

    def _deny(self, reason: str, risk: str, path: str = "") -> ValidationResult:
        return ValidationResult(allowed=False, reason=reason, risk_level=risk, normalized_path=path)

    def _allow(self, path: str, risk: str = "low") -> ValidationResult:
        return ValidationResult(allowed=True, reason="", risk_level=risk, normalized_path=path)

    def _normalize(self, path: str) -> str:
        expanded = os.path.expandvars(os.path.expanduser(path))
        normalized = os.path.normpath(expanded)
        if not os.path.isabs(normalized):
            normalized = os.path.abspath(normalized)
        return normalized

    def _has_traversal(self, path: str) -> bool:
        sep = os.sep
        parts = path.replace("/", sep).split(sep)
        if ".." in parts:
            return True
        if re.search(r"(?:^|[/\\])\.\.(?:[/\\]|$)", path):
            return True
        return False

    def _resolve_symlink(self, path: str) -> str:
        try:
            if os.path.islink(path):
                target = os.readlink(path)
                if target.startswith("\\\\?\\"):
                    target = target[4:]
                if not os.path.isabs(target):
                    target = os.path.abspath(os.path.join(os.path.dirname(path), target))
                resolved = os.path.normpath(target)
                log.debug("Symlink %s -> %s", path, resolved)
                return resolved
        except OSError as e:
            log.debug("Symlink resolution failed for %s: %s", path, e)
        return path

    def _check_sensitive(self, path: str) -> Optional[str]:
        name = os.path.basename(path)
        matched, pattern = is_sensitive_filename(name)
        if matched:
            return f"File matches sensitive pattern: '{pattern}'"
        for part in path.split(os.sep):
            matched, pattern = is_sensitive_filename(part)
            if matched:
                return f"Path component matches sensitive pattern: '{pattern}'"
        return None

    def _assess_risk(self, operation: str, path: str) -> str:
        if operation == "delete":
            return "high"
        if operation == "write":
            lower = path.lower()
            if any(k in lower for k in ["boot", "system", "config"]):
                return "high"
            return "medium"
        return "low"
