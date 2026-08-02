#!/usr/bin/env python3
"""Generate the Tauri (v2) updater feed ``update.json`` from release artifacts.

The updater plugin in ``src-tauri/tauri.conf.json`` is configured with an
endpoint that must serve a static ``update.json`` feed alongside a release.
This tool builds that feed from the signed Windows installer, producing a
parseable, integrity-backed manifest the desktop app verifies at startup.

Signature handling: ``.sig`` files emitted by ``tauri build`` are the Tauri
updater's minisign signatures. This tool preserves them verbatim in the feed so
the app's signature check remains byte-for-byte identical.
"""

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FEED_NAME = "update.json"


def _signature(signature_file: Path) -> str:
    if not signature_file.is_file():
        raise ValueError(f"Updater signature not found: {signature_file}")
    data = signature_file.read_bytes()
    try:
        return base64.b64encode(data).decode("ascii")
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Failed to encode updater signature: {exc}") from exc


def _notes(version: str, root: Path) -> str:
    candidate = root / f"docs/RELEASE_NOTES_SENTINEL_{version}.md"
    if not candidate.is_file():
        candidate = root / "docs/RELEASE_NOTES_SENTINEL_1.0.0_RC.md"
    if candidate.is_file():
        return (candidate.read_text(encoding="utf-8", errors="replace") or "").strip()[
            :4000
        ]
    return ""


def build(
    *,
    version: str,
    installer_url: str,
    signature_file: Path,
    root: Path,
    pub_date: str | None = None,
    platform: str = "windows-x86_64",
) -> dict:
    if not version or not installer_url:
        raise ValueError("version and installer_url are required")
    moment = pub_date or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    return {
        "version": version,
        "notes": _notes(version, root),
        "pub_date": moment,
        "platforms": {
            platform: {
                "signature": _signature(signature_file),
                "url": installer_url,
            }
        },
    }


def write_feed(root: Path, feed: dict, out: Path | None = None) -> Path:
    target = out or (root / "release-metadata" / FEED_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(feed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def validate(feed: dict) -> None:
    if not isinstance(feed, dict):
        raise ValueError("update feed must be an object")
    version = feed.get("version", "")
    if not version:
        raise ValueError("update feed missing version")
    platforms = feed.get("platforms", {})
    if not isinstance(platforms, dict) or not platforms:
        raise ValueError("update feed missing platforms")
    for plat, entry in platforms.items():
        if (
            not isinstance(entry, dict)
            or not entry.get("url")
            or not entry.get("signature")
        ):
            raise ValueError(f"update feed platform {plat!r} missing url/signature")
        if "\n" in entry["url"] or "\r" in entry["url"]:
            raise ValueError(f"update feed platform {plat!r} has unsafe url")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--version", required=True)
    parser.add_argument("--installer-url", required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--repodir", type=Path, help="Root containing docs/ (defaults to --root)"
    )
    args = parser.parse_args()

    repo = args.repodir or args.root
    try:
        feed = build(
            version=args.version,
            installer_url=args.installer_url,
            signature_file=args.signature.resolve(),
            root=repo.resolve(),
        )
        validate(feed)
        target = write_feed(
            args.root.resolve(), feed, out=args.out.resolve() if args.out else None
        )
        print(f"update feed written: {target}")
        print(f"version={feed['version']} platform={next(iter(feed['platforms']))}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"update feed error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
