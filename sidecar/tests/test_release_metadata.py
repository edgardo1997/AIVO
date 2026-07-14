import json
from pathlib import Path

import pytest

from scripts.release_metadata import generate, verify


def _sbom(path: Path, component: str) -> None:
    path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [{"type": "library", "name": component, "version": "1.0.0"}],
            }
        ),
        encoding="utf-8",
    )


def test_release_metadata_detects_single_byte_tampering(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"version":"1.0.0"}', encoding="utf-8")
    bundles = tmp_path / "bundles"
    metadata = tmp_path / "release-metadata"
    bundles.mkdir()
    metadata.mkdir()
    installer = bundles / "Sentinel_1.0.0_x64-setup.exe"
    installer.write_bytes(b"trusted-installer")
    (bundles / "Sentinel_1.0.0_x64-setup.exe.sig").write_text("signature", encoding="utf-8")
    for name in ("sbom-npm.cdx.json", "sbom-python.cdx.json", "sbom-rust.cdx.json"):
        _sbom(metadata / name, name)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    manifest = generate(tmp_path, bundles, metadata)
    verify(tmp_path, manifest)

    installer.write_bytes(b"trusted-installeR")
    with pytest.raises(ValueError, match="Integrity verification failed"):
        verify(tmp_path, manifest)
