"""Central secret redactor for diagnostic exports and user-facing messages."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional

DEFAULT_SENSITIVE_KEYS = [
    "authorization",
    "bearer",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "private_key",
    "client_secret",
    "cookie",
    "session",
    "vault",
    "credential",
    "api-key",
]

URL_WITH_CREDS_RE = re.compile(
    r"([a-zA-Z][a-zA-Z0-9+.-]*)://"
    r"([^:@]+):([^@]+)@"
    r"([^\s\"'<>]+)",
    re.IGNORECASE,
)

TOKEN_RE = re.compile(
    r"(bearer\s+)?"
    r"([a-zA-Z0-9_\-]+(?:_|-)?(?:token|key|secret|password|auth|api_key|apikey|access_token|refresh_token))"
    r"(?:\s*[:=]\s*|\s+)"
    r"([\"']?)([a-zA-Z0-9_\-]{8,})(\3)",
    re.IGNORECASE,
)

USERPROFILE_RE = re.compile(
    r"([A-Za-z]:\\(?:Users|home|Documents and Settings)\\[^\\]+)(\\.*)",
    re.IGNORECASE,
)


class SecretRedactor:
    """Redacts secrets and normalizes paths in arbitrary payloads."""

    def __init__(
        self,
        sensitive_keys: Optional[List[str]] = None,
        replacement: str = "[REDACTED]",
    ) -> None:
        self.sensitive_keys = {k.lower() for k in (sensitive_keys or DEFAULT_SENSITIVE_KEYS)}
        self.replacement = replacement

    def redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redact_text(value)
        if isinstance(value, dict):
            return {k: self._redact_value(k, v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.redact(v) for v in value)
        return value

    def _redact_value(self, key: str, value: Any) -> Any:
        if isinstance(key, str) and key.lower() in self.sensitive_keys:
            return self.replacement
        return self.redact(value)

    def _redact_text(self, text: str) -> str:
        # URLs with credentials
        text = URL_WITH_CREDS_RE.sub(lambda m: f"{m.group(1)}://{self.replacement}@{m.group(4)}", text)
        # Token-like key=secret and "key":"secret" patterns
        text = TOKEN_RE.sub(lambda m: f"{m.group(2)}={m.group(3)}{self.replacement}{m.group(5)}", text)
        # Environment variables with sensitive names
        for key in self.sensitive_keys:
            pattern = re.compile(rf"({re.escape(key)}[A-Z0-9_]*\s*[:=]\s*)([^\s\"'\n]{{4,}})", re.IGNORECASE)
            text = pattern.sub(lambda m: f"{m.group(1)}{self.replacement}", text)
        return text

    def normalize_paths(self, text: str, user_home: Optional[str] = None) -> str:
        home = user_home or os.path.expanduser("~")
        home_lower = home.lower().rstrip("\\/")
        pattern = re.compile(re.escape(home_lower) + r"(\\.*)", re.IGNORECASE)
        text = pattern.sub(r"%USERPROFILE%\1", text)
        text = USERPROFILE_RE.sub(r"%USERPROFILE%\2", text)
        return text


def redact_secrets(value: Any, replacement: str = "[REDACTED]") -> Any:
    return SecretRedactor(replacement=replacement).redact(value)


def redact_paths(text: str, user_home: Optional[str] = None) -> str:
    return SecretRedactor().normalize_paths(text, user_home)


def redact_for_export(text: str, user_home: Optional[str] = None, replacement: str = "[REDACTED]") -> str:
    redacted = SecretRedactor(replacement=replacement).redact(text)
    if isinstance(redacted, str):
        return redact_paths(redacted, user_home)
    return json.dumps(redacted, ensure_ascii=False)
