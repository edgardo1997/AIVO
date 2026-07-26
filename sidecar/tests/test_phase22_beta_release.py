from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.security
def test_private_beta_is_manual_protected_and_prerelease():
    workflow = (ROOT / ".github/workflows/publish-beta.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "environment: private-beta" in workflow
    assert "PRIVATE_BETA_APPROVED" in workflow
    assert "--draft=false --prerelease" in workflow
    assert "push:" not in workflow


@pytest.mark.security
def test_beta_requires_pentest_signed_candidate_and_rollback():
    workflow = (ROOT / ".github/workflows/publish-beta.yml").read_text(encoding="utf-8")
    assert "verify_pentest_gate.py" in workflow
    assert "verify-downloaded" in workflow
    assert "Get-AuthenticodeSignature" in workflow
    assert "gh attestation verify" in workflow
    assert "ROLLBACK_TAG" in workflow
    assert "No rollback-capable installer" in workflow


@pytest.mark.security
def test_release_smoke_is_isolated_and_uses_current_contract():
    smoke = (ROOT / "scripts/smoke-release.ps1").read_text(encoding="utf-8")
    assert "TcpListener" in smoke
    assert 'SENTINEL_PORT = "$smokePort"' in smoke
    assert '$health.status -eq "healthy"' in smoke
    assert '"plugins.list"' in smoke
    assert "plugins.load" not in smoke
    assert "127.0.0.1:8765" not in smoke


@pytest.mark.security
def test_beta_runbook_prohibits_sensitive_support_payloads():
    runbook = (ROOT / "docs/BETA_OPERATIONS.md").read_text(encoding="utf-8")
    for forbidden in ("tokens", "prompts", "comandos", "rutas privadas", "credenciales"):
        assert forbidden in runbook
    assert "periodo estable" in runbook
    assert "pentest independiente aprobado" in runbook
    assert "VM limpia" in runbook
