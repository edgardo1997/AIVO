import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_versions_are_consistent():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo = (ROOT / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    main = (ROOT / "sidecar" / "main.py").read_text(encoding="utf-8")
    version = package["version"]
    assert version == "1.0.0"
    assert tauri["version"] == version
    assert re.search(rf'^version = "{re.escape(version)}"$', cargo, re.MULTILINE)
    assert f'"version": "{version}"' in main


def test_updater_requires_signed_artifacts():
    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    updater = tauri["plugins"]["updater"]
    assert tauri["bundle"]["createUpdaterArtifacts"] is True
    assert updater["pubkey"].strip()
    assert updater["endpoints"][0].startswith("https://")


def test_release_pipeline_smoke_tests_packaged_binary():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "smoke-release.ps1" in workflow
    assert "TAURI_SIGNING_PRIVATE_KEY" in workflow
    assert "includeUpdaterJson: true" in workflow
    assert "releaseDraft: true" in workflow


def test_installer_contains_sidecar_and_onboarding():
    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert "../sidecar/dist/sidecar.exe" in tauri["bundle"]["resources"]
    app = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "sentinel.onboarding.v1" in app


def test_packaged_runtime_dependencies_are_explicit():
    requirements = (ROOT / "sidecar" / "requirements.txt").read_text(encoding="utf-8")
    spec = (ROOT / "sidecar" / "sidecar.spec").read_text(encoding="utf-8")
    assert "SQLAlchemy==2.0.36" in requirements
    assert "aiosqlite==0.20.0" in requirements
    assert "'aiosqlite'" in spec


def test_windows_acl_hardening_is_packaged_and_documented():
    spec = (ROOT / "sidecar" / "sidecar.spec").read_text(encoding="utf-8")
    main = (ROOT / "sidecar" / "main.py").read_text(encoding="utf-8")
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    assert "sidecar.windows_acl" in spec
    assert "secure_runtime_directories()" in main
    assert "ACL de Windows" in deployment


def test_release_requires_both_update_and_authenticode_signatures():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "WINDOWS_CERTIFICATE_PASSWORD" in workflow
    assert "1.3.6.1.5.5.7.3.3" in workflow
    assert "Get-AuthenticodeSignature" in workflow
    assert "updaterSignatures" in workflow


def test_release_generates_sboms_hashes_and_provenance():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    metadata = (ROOT / "scripts" / "release_metadata.py").read_text(encoding="utf-8")
    assert "@cyclonedx/cyclonedx-npm@4.2.1" in workflow
    assert "cyclonedx-bom==7.3.0" in workflow
    assert "cargo-cyclonedx --version 0.5.9" in workflow
    assert "--override-filename sbom-rust.cdx\n" in workflow
    assert "--override-filename sbom-rust.cdx.json" not in workflow
    assert "actions/attest@v4" in workflow
    assert "attestations: write" in workflow
    assert "id-token: write" in workflow
    assert "artifact-metadata: write" in workflow
    assert "SHA256SUMS" in metadata
    assert "SBOM_NAMES" in metadata
    assert "gh release upload" in workflow
