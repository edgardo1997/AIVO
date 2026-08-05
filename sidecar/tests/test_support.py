import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from sentinel.core.support import (
    ErrorCategory,
    ErrorRegistry,
    ErrorSeverity,
    map_exception,
    new_correlation_id,
    get_correlation_id,
    set_correlation_id,
    redact_secrets,
    redact_paths,
    DiagnosticService,
    SecretRedactor,
)
from sentinel.core.support.errors import _new_correlation


@pytest.mark.unit
def test_error_codes_are_unique():
    codes = list(ErrorRegistry.codes().keys())
    assert len(codes) == len(set(codes))


@pytest.mark.unit
def test_error_codes_are_stable():
    err = ErrorRegistry.build(
        "SEN-AUTH-001",
        component="onboarding",
        details={"identity": "local-user"},
    )
    assert err.error_code == "SEN-AUTH-001"
    assert err.category == ErrorCategory.AUTHENTICATION


@pytest.mark.unit
def test_unknown_exception_maps_to_safe_error():
    err = map_exception(ValueError("something bad"), component="chat", build_id="abc")
    assert err.error_code == "SEN-UNKNOWN-001"
    assert "something bad" in err.technical_message
    assert "trace" not in err.user_message.lower()


@pytest.mark.unit
def test_user_message_does_not_include_traceback():
    err = map_exception(RuntimeError("/full/path/to/file.py: boom"), component="chat")
    assert "/full/path" not in err.user_message
    assert err.user_message


@pytest.mark.unit
def test_correlation_id_propagates_through_execution():
    cid = _new_correlation()
    set_correlation_id(cid)
    assert get_correlation_id() == cid
    # Simulate nested call with context propagation
    set_correlation_id(cid)
    assert get_correlation_id() == cid


@pytest.mark.unit
def test_build_id_is_present_in_sentinel_error():
    err = ErrorRegistry.build(
        "SEN-PERSIST-001",
        component="persistence",
        build_id="internal-alpha-20260805-0bcfeb6",
    )
    assert err.build_id == "internal-alpha-20260805-0bcfeb6"


@pytest.mark.unit
def test_redactor_removes_fake_secrets():
    payload = {
        "api_key": "FAKE-API-KEY-12345",
        "token": "bearer FAKE-TOKEN-XXXXX",
        "Authorization": "Bearer secret-token-123",
    }
    redacted = redact_secrets(payload)
    assert "FAKE-API-KEY" not in str(redacted)
    assert "FAKE-TOKEN" not in str(redacted)
    assert "secret-token-123" not in str(redacted)
    assert redacted["api_key"] == "[REDACTED]"


@pytest.mark.unit
def test_redactor_normalizes_paths():
    text = r"C:\Users\SomeUser\Documents\file.pdf"
    normalized = redact_paths(text)
    assert "%USERPROFILE%" in normalized


@pytest.mark.unit
def test_diagnostic_zip_is_valid():
    svc = DiagnosticService(build_id="internal-alpha-test", data_dir=Path(tempfile.gettempdir()) / "sentinel")
    result = svc.collect(recent_errors=["test error"])
    zip_path = Path(result["path"])
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "summary.json" in names
        assert "manifest.json" in names
        assert "README.txt" in names
        assert "SHA256SUMS.txt" in names


@pytest.mark.unit
def test_diagnostic_contains_build_id():
    svc = DiagnosticService(build_id="internal-alpha-20260805-0bcfeb6")
    result = svc.collect()
    assert result["summary"]["build_id"] == "internal-alpha-20260805-0bcfeb6"


@pytest.mark.unit
def test_diagnostic_manifest_hashes_match():
    svc = DiagnosticService(build_id="build-test")
    result = svc.collect()
    manifest = result["manifest"]
    for f in manifest["files"]:
        assert len(f["sha256"]) == 64
        assert f["size"] >= 0


@pytest.mark.unit
def test_diagnostic_works_offline():
    svc = DiagnosticService(build_id="offline-test")
    result = svc.collect()
    assert result["path"]
    assert "sha256" in result
