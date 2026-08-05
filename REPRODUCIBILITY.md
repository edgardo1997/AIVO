# Sentinel Reproducibility Contract

This document defines how to reconstruct the Sentinel development and build environment from source.

## Source of truth

- **Repository:** `https://github.com/edgardo1997/AIVO.git`
- **Branch:** `main`
- **Tag:** `v0.1.0-alpha.1`

## Pinning

| Stack | File | Command |
| ----- | ---- | ------- |
| Python | `.python-version` | `python -m uv sync --frozen` |
| Python deps | `pyproject.toml` + `uv.lock` | `uv lock` / `uv sync --frozen` |
| Node | `.nvmrc` + `package.json` `engines` | `npm ci` |
| Node deps | `package-lock.json` | `npm ci` |
| Rust | `rust-toolchain.toml` | `rustup show` |
| Rust deps | `src-tauri/Cargo.lock` | `cargo build --locked` |

## What is not versioned

- `.env` (create from `.env.example`)
- `vault.key`
- `*.db`, `*.db-wal`, `*.db-shm`
- `sentinel/local_model/` (download via `scripts/download_local_model.py`)
- `.venv/`, `node_modules/`, `src-tauri/target/`, `sidecar/dist/`
- `.local-data/`
- logs and caches

## Reproducing from a clean clone

```powershell
git clone https://github.com/edgardo1997/AIVO.git C:\Dev\AIVO
cd C:\Dev\AIVO
Copy-Item .env.example .env
.\scripts\bootstrap-dev.ps1
.\scripts\verify-environment.ps1
python -m uv run python -m pytest -m alpha_constitutional_gate -q
npm test
npm run build
cargo test --locked --manifest-path src-tauri/Cargo.toml
```

## Verifying the environment

Use the verification script to confirm all required components:

```powershell
.\scripts\verify-environment.ps1
```

It reports `OK`/`FAIL` for each component and exits with `0` only when everything is in place.

## Model assets

The local model is an external asset. It is not committed. The official download helper validates SHA-256 and performs an atomic move:

```powershell
python scripts/download_local_model.py --url <URL> --sha256 <SHA256>
```

## Current limitations

- The build of the Tauri/Rust crate requires `sidecar/dist/sidecar.exe` to be built first via `pyinstaller`.
- The default build channel is `alpha`; test mode is disabled via `SENTINEL_DISABLE_TEST_MODE=1`.
