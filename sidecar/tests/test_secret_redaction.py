"""FASE 14 — Secret and PII redaction tests for diagnostics."""

import json
import re

import pytest

pytestmark = pytest.mark.stability


def _redact(text: str) -> str:
    """Minimal redactor for diagnostic outputs.

    This is a reference implementation for tests; the product should use
    a central redactor that covers the same patterns.
    """
    # Bearer tokens
    text = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", text)
    # sk- keys (OpenAI-style)
    text = re.sub(r"sk-[A-Za-z0-9_\-]+", r"[REDACTED]", text)
    # JSON key: "value" secret-like keys
    text = re.sub(
        r'(?i)"(api[_-]?key|secret|password|token|client_secret|private_key)"(\s*:\s*")[^"]*"',
        r'"\1"\2[REDACTED]"',
        text,
    )
    # key=value or key: value (plain)
    text = re.sub(
        r"(?i)(api[_-]?key|secret|password|token|client_secret|private_key)\s*[:=]\s*[^\s,}\]]+",
        r"\1=[REDACTED]",
        text,
    )
    # Paths with user profile
    text = re.sub(r"C:\\Users\\[^\\]+", r"C:\\Users\\[REDACTED]", text)
    return text


def test_redacts_bearer_token():
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc"
    assert _redact(raw) == "Authorization: Bearer [REDACTED]"


def test_redacts_api_key_json():
    raw = '{"api_key": "sk-1234567890abcdef", "name": "test"}'
    out = _redact(raw)
    assert "sk-1234567890abcdef" not in out
    assert "[REDACTED]" in out
    assert '"name": "test"' in out


def test_redacts_password():
    raw = "password=my_secret_123"
    out = _redact(raw)
    assert "my_secret_123" not in out
    assert "[REDACTED]" in out


def test_redacts_user_profile_path():
    raw = "C:\\Users\\Edgardo\\Documents\\file.pdf"
    out = _redact(raw)
    assert "Edgardo" not in out
    assert "C:\\Users\\[REDACTED]" in out


def test_redactor_does_not_corrupt_non_secrets():
    raw = '{"message": "hello", "value": 123}'
    assert _redact(raw) == raw
