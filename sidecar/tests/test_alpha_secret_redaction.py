import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentinel.security.secret_redaction import redact, redact_text, SecretRedactionFilter


def test_redact_api_key_in_dict():
    data = {"provider": "openrouter", "api_key": "sk-1234567890abcdef1234567890"}
    result = redact(data)
    assert result["api_key"] == "[REDACTED]"
    assert result["provider"] == "openrouter"


def test_redact_bearer_in_string():
    text = "Authorization: Bearer abcdef1234567890abcdef1234567890"
    assert "[REDACTED]" in redact_text(text)
    assert "abcdef1234567890" not in redact_text(text)


def test_logging_filter_redacts_args(tmp_path):
    log_path = tmp_path / "redaction.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test_redaction_logger")
    logger.addHandler(handler)
    logger.addFilter(SecretRedactionFilter())
    logger.setLevel(logging.INFO)

    fake_key = "sk-redaction-test-1234567890abcdef"
    logger.info("Provider configured with key %s", fake_key)

    handler.close()
    logger.removeHandler(handler)

    content = log_path.read_text(encoding="utf-8")
    assert fake_key not in content
    assert "[REDACTED]" in content
