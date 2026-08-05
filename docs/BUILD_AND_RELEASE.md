# Sentinel Build and Release Pipeline

This document defines the canonical build pipeline for Sentinel on Windows.

## Single command

```powershell
.\scripts\build-alpha.ps1
```

For development builds from a dirty working tree:

```powershell
.\scripts\build-alpha.ps1 -AllowDirty
```

To skip Tauri bundling:

```powershell
.\scripts\build-alpha.ps1 -SkipTauri
```

## Requirements

- Windows 11 x64
- Python 3.12.10
- Node 20+
- npm 10+
- Rust 1.96+
- `uv` installed
- Git

## Canonical sidecar path

```text
<repo>/sidecar/dist/sidecar.exe
```

This is the only official location.

- `sidecar.spec` produces it.
- `tauri.conf.json` bundles it.
- `src-tauri/build.rs` validates it before the Tauri build.
- `src-tauri/src/lib.rs` looks for it at runtime.
- `scripts/smoke-sidecar.ps1` tests it.

## Pipeline

```text
verify source
  ↓
clean regenerable artifacts
  ↓
npm ci
  ↓
npm run build
  ↓
python -m uv sync --frozen
  ↓
PyInstaller sidecar.spec
  ↓
sidecar smoke
  ↓
sidecar SHA-256
  ↓
cargo test
  ↓
cargo clippy
  ↓
cargo fmt --check
  ↓
npm run tauri:build
  ↓
extract/inspect bundled sidecar
  ↓
hash comparison
  ↓
artifacts/alpha-manifest.json
```

## Versioning

Source of truth:

- `package.json` for Node/frontend
- `src-tauri/Cargo.toml` for Rust
- `src-tauri/tauri.conf.json` for Tauri bundle metadata
- `pyproject.toml` for Python package

Runtime sidecar version is reported by `sidecar/main.py` and must match the canonical version.

Current Alpha version: `0.1.0-alpha.1`.

## Channels

| Channel | Dirty allowed | Updater | Signing |
| ------- | ------------- | ------- | ------- |
| `development` | yes (flag) | disabled | none |
| `alpha` | no | disabled | none |
| `release` | no | enabled | Authenticode + updater key |

## Updater

Alpha builds disable updater artifact creation:

```json
{
  "bundle": {
    "createUpdaterArtifacts": false
  }
}
```

Release builds require `TAURI_SIGNING_PRIVATE_KEY`.

## Artifacts

After a successful build:

```text
artifacts/alpha-manifest.json
src-tauri/target/release/bundle/...
```

The manifest contains:

- product, version, channel
- commit, branch, build_id, timestamp
- sidecar canonical path and SHA-256
- bundled artifact names, sizes and hashes

## Troubleshooting

### Tauri bundle does not find sidecar

Ensure `sidecar/dist/sidecar.exe` exists and is fresh before `npm run tauri:build`.
The `build.rs` script refuses to continue if the executable is missing.

### Hash mismatch

If the sidecar bundled by Tauri differs from the canonical one, the build fails.
Do not copy `sidecar.exe` manually between folders. Use the pipeline.

### Updater signing error

For Alpha, `createUpdaterArtifacts` is disabled. Do not set `TAURI_SIGNING_PRIVATE_KEY` unless building a release.
