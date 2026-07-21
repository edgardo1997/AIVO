from pathlib import Path

from scripts.release_metadata import SBOM_NAMES, release_files


def test_release_files_includes_updater_archives_when_present(tmp_path: Path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in (
        "Sentinel-setup.exe",
        "Sentinel-setup.exe.sig",
        "Sentinel-updater.nsis.zip",
        "Sentinel-updater.tar.gz",
        "ignored-debug.log",
    ):
        (bundle / name).write_bytes(name.encode("utf-8"))

    sboms = []
    for name in sorted(SBOM_NAMES):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        sboms.append(path)

    selected = {path.name for path in release_files(bundle, sboms)}

    assert "Sentinel-updater.nsis.zip" in selected
    assert "Sentinel-updater.tar.gz" in selected
    assert "ignored-debug.log" not in selected
    assert SBOM_NAMES.issubset(selected)
