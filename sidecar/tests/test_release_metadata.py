import json
from pathlib import Path

import pytest

from scripts.release_metadata import generate, verify, verify_downloaded


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


def test_downloaded_release_assets_are_reverified_before_publication(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"version":"1.0.0"}', encoding="utf-8")
    bundles = tmp_path / "bundles"
    metadata = tmp_path / "release-metadata"
    downloaded = tmp_path / "downloaded"
    bundles.mkdir()
    metadata.mkdir()
    downloaded.mkdir()
    installer = bundles / "Sentinel_1.0.0_x64-setup.exe"
    installer.write_bytes(b"trusted-installer")
    signature = bundles / "Sentinel_1.0.0_x64-setup.exe.sig"
    signature.write_text("signature", encoding="utf-8")
    for name in ("sbom-npm.cdx.json", "sbom-python.cdx.json", "sbom-rust.cdx.json"):
        _sbom(metadata / name, name)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    manifest = generate(tmp_path, bundles, metadata)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    for record in document["artifacts"]:
        source = tmp_path / record["path"]
        (downloaded / source.name).write_bytes(source.read_bytes())
    (downloaded / "release-manifest.json").write_bytes(manifest.read_bytes())
    (downloaded / "SHA256SUMS").write_bytes((metadata / "SHA256SUMS").read_bytes())

    verify_downloaded(downloaded / "release-manifest.json", downloaded)
    (downloaded / installer.name).write_bytes(b"substituted-installer")
    with pytest.raises(ValueError, match="Downloaded release asset failed"):
        verify_downloaded(downloaded / "release-manifest.json", downloaded)
