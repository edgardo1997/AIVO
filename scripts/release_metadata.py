#!/usr/bin/env python3
"""Generate and verify Sentinel release integrity metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = "https://sentinel.local/schemas/release-manifest/v1"
SBOM_NAMES = {
    "sbom-npm.cdx.json",
    "sbom-python.cdx.json",
    "sbom-rust.cdx.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_name(path: Path, root: Path) -> str:
    name = path.resolve().relative_to(root.resolve()).as_posix()
    if "\n" in name or "\r" in name:
        raise ValueError(f"Unsafe release artifact name: {name!r}")
    return name


def validate_sboms(metadata_dir: Path) -> list[Path]:
    paths = [metadata_dir / name for name in sorted(SBOM_NAMES)]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"Missing required SBOMs: {', '.join(missing)}")
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("bomFormat") != "CycloneDX":
            raise ValueError(f"{path.name} is not a CycloneDX SBOM")
        if not document.get("specVersion") or not document.get("components"):
            raise ValueError(f"{path.name} has no specification version or components")
    return paths


def git_commit(root: Path) -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def generated_at() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    moment = datetime.fromtimestamp(int(epoch), timezone.utc) if epoch else datetime.now(timezone.utc)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def release_files(artifact_root: Path, sboms: Iterable[Path]) -> list[Path]:
    artifacts = [
        path
        for path in artifact_root.rglob("*")
        if path.is_file() and (path.suffix.lower() in {".exe", ".msi", ".sig"} or path.name == "update.json")
    ]
    if not any(path.suffix.lower() in {".exe", ".msi"} for path in artifacts):
        raise ValueError("No Windows installer artifacts were found")
    if not any(path.suffix.lower() == ".sig" for path in artifacts):
        raise ValueError("No updater signature artifacts were found")
    return sorted({*artifacts, *sboms}, key=lambda item: item.as_posix())


def generate(root: Path, artifact_root: Path, metadata_dir: Path) -> Path:
    metadata_dir.mkdir(parents=True, exist_ok=True)
    sboms = validate_sboms(metadata_dir)
    files = release_files(artifact_root, sboms)
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    records = []
    for path in files:
        records.append(
            {
                "path": relative_name(path, root),
                "sha256": sha256(path),
                "size": path.stat().st_size,
            }
        )
    manifest = {
        "$schema": SCHEMA,
        "product": "Sentinel",
        "version": package["version"],
        "source": {"repository": os.environ.get("GITHUB_REPOSITORY", "edgardo1997/AIVO"), "commit": git_commit(root)},
        "generatedAt": generated_at(),
        "artifacts": records,
    }
    manifest_path = metadata_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = metadata_dir / "SHA256SUMS"
    checksums.write_text("".join(f"{item['sha256']}  {item['path']}\n" for item in records), encoding="utf-8")
    return manifest_path


def verify(root: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("$schema") != SCHEMA or manifest.get("product") != "Sentinel":
        raise ValueError("Unsupported or invalid Sentinel release manifest")
    package_version = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
    if manifest.get("version") != package_version:
        raise ValueError("Release manifest version does not match package.json")
    records = manifest.get("artifacts")
    if not isinstance(records, list) or not records:
        raise ValueError("Release manifest contains no artifacts")
    seen: set[str] = set()
    for record in records:
        name = record.get("path", "")
        if name in seen or not name or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError(f"Duplicate or unsafe artifact path: {name!r}")
        seen.add(name)
        path = root / name
        if not path.is_file():
            raise ValueError(f"Missing release artifact: {name}")
        if path.stat().st_size != record.get("size") or sha256(path) != record.get("sha256"):
            raise ValueError(f"Integrity verification failed: {name}")
    if not SBOM_NAMES.issubset({Path(name).name for name in seen}):
        raise ValueError("Release manifest does not contain every required SBOM")
    if not any(Path(name).suffix.lower() in {".exe", ".msi"} for name in seen):
        raise ValueError("Release manifest contains no Windows installer")
    if not any(Path(name).suffix.lower() == ".sig" for name in seen):
        raise ValueError("Release manifest contains no updater signature")
    checksums_path = manifest_path.parent / "SHA256SUMS"
    expected = "".join(f"{record['sha256']}  {record['path']}\n" for record in records)
    if checksums_path.read_text(encoding="utf-8") != expected:
        raise ValueError("SHA256SUMS does not match the signed release manifest")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--root", type=Path, default=Path.cwd())
    generate_parser.add_argument("--artifact-root", type=Path, required=True)
    generate_parser.add_argument("--metadata-dir", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, default=Path.cwd())
    verify_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            print(generate(args.root.resolve(), args.artifact_root.resolve(), args.metadata_dir.resolve()))
        else:
            verify(args.root.resolve(), args.manifest.resolve())
            print("Sentinel release hashes and manifest verified")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"release metadata error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
