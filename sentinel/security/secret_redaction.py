import logging
import re
from typing import Any, Dict, List, Optional


_SECRET_KEYS = (
    "api_key",
    "apikey",
    "api-key",
    "bearer",
    "token",
    "auth_token",
    "refresh_token",
    "password",
    "secret",
    "client_secret",
    "connection_string",
    "session_secret",
    "authorization",
    "x-api-key",
    "api_key",
)

_SECRET_PATTERNS = (
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9]{32,}-[a-zA-Z0-9]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*Bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
)

_REDACTED = "[REDACTED]"


def _is_secret_key(key: str) -> bool:
    k = key.lower().replace("-", "_")
    for secret in _SECRET_KEYS:
        if secret.lower().replace("-", "_") in k:
            return True
    return False


def redact(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub(_REDACTED, value)
        return value
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if _is_secret_key(k) and isinstance(v, str):
                result[k] = _REDACTED
            else:
                result[k] = redact(v)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def redact_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(redact(arg) for arg in record.args)
        record.msg = redact_text(record.msg)
        record.message = redact_text(record.getMessage())
        return True
