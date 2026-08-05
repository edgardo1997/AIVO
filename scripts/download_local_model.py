"""Official helper to download and verify the Sentinel local model.

This script does not download unless a source URL and expected SHA-256 are
provided. It is meant to be invoked explicitly by the developer or by the
Sentinel onboarding flow once that is implemented.

Example:
    python scripts/download_local_model.py \
        --url https://example.com/models/model.gguf \
        --sha256 abc123... \
        --output-dir sentinel/local_model
"""
import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("invalid URL")

    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify Sentinel local model")
    parser.add_argument("--url", required=True, help="HTTPS URL of the model file")
    parser.add_argument("--sha256", required=True, help="Expected SHA-256 hex digest")
    parser.add_argument("--output-dir", default="sentinel/local_model", help="Destination directory")
    parser.add_argument("--filename", default="model.gguf", help="Output filename")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / args.filename

    with tempfile.TemporaryDirectory(dir=output_dir, prefix=".download-") as tmp:
        tmp_path = Path(tmp) / "download.tmp"
        print(f"Downloading {args.url} ...")
        download(args.url, tmp_path)

        print("Verifying SHA-256 ...")
        actual = sha256_file(tmp_path)
        if actual.lower() != args.sha256.lower():
            print(f"Hash mismatch: expected {args.sha256}, got {actual}", file=sys.stderr)
            return 1

        # Atomic-ish move
        os.replace(tmp_path, final_path)

    print(f"Model saved to {final_path}")
    print(f"SHA-256: {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
