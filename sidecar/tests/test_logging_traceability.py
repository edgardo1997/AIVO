"""Tests for structured logging, build_id and correlation_id propagation."""

import json
import logging
import re
from pathlib import Path
from unittest.mock import patch

from sentinel.core.support.correlation import (
    new_correlation_id,
    set_correlation_id,
)
from sentinel.core.support.logger import log_structured, setup_structured_logging
from sentinel.security.secret_redaction import SecretRedactionFilter


def _parse_jsonl(path: Path):
    lines = []
    if not path.exists():
        return lines
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                pass
    return lines


def test_setup_structured_logging_emits_build_id_and_correlation_id(tmp_path: Path):
    log_file = tmp_path / "test.jsonl"
    setup_structured_logging(
        build_id="internal-alpha-2026-test",
        log_dir=tmp_path,
        log_file=log_file,
    )
    new_correlation_id()
    log_structured("INFO", "test", "test_event", "hello", build_id="internal-alpha-2026-test")

    records = _parse_jsonl(log_file)
    assert records, "No JSONL records emitted"
    assert records[-1]["build_id"] == "internal-alpha-2026-test"
    assert records[-1]["correlation_id"]
    # log_structured emits its own JSON inside the message field
    inner = json.loads(records[-1]["message"])
    assert inner["event"] == "test_event"
    assert inner["build_id"] == "internal-alpha-2026-test"


def test_build_id_in_plain_log_records(tmp_path: Path):
    log_file = tmp_path / "plain.jsonl"
    setup_structured_logging(
        build_id="internal-alpha-2026-plain",
        log_dir=tmp_path,
        log_file=log_file,
    )
    new_correlation_id()
    logger = logging.getLogger("plain_component")
    logger.handlers = []
    logger.propagate = True
    logger.info("plain message")

    records = _parse_jsonl(log_file)
    assert records, "No records for plain logger"
    assert records[-1]["build_id"] == "internal-alpha-2026-plain"
    assert records[-1]["correlation_id"]
    assert "plain message" in records[-1]["message"]


def test_secret_redaction_filter_redacts_token():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="sk-12345678901234567890 secret",
        args=(),
        exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert "sk-" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage() or "sk-" not in record.getMessage()


def test_secret_redaction_filter_redacts_jwt():
    token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc"
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=token,
        args=(),
        exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    output = record.getMessage()
    assert "eyJhbGci" not in output or output.count("eyJhbGci") == 0


def test_diagnostic_excludes_fake_secrets(client, tmp_path):
    import zipfile
    from io import BytesIO

    from fastapi.testclient import TestClient

    r = client.post("/api/support/diagnostic", json={})
    assert r.status_code == 200
    data = r.json()
    assert data["success"]

    zip_path = Path(data["path"])
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        full_text = ""
        for name in zf.namelist():
            try:
                full_text += zf.read(name).decode("utf-8", errors="ignore")
            except Exception:
                pass
    for secret in [
        "FAKE_API_KEY_SENTINEL_TEST",
        "FAKE_BEARER_TOKEN_SENTINEL_TEST",
        "FAKE_PASSWORD_SENTINEL_TEST",
        "FAKE_PRIVATE_KEY_SENTINEL_TEST",
        "FAKE_COOKIE_SENTINEL_TEST",
    ]:
        assert secret not in full_text
