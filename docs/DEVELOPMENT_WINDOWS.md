# Sentinel Development Environment — Windows

This document describes how to build and test Sentinel on Windows from a clean clone.

## Supported target

- Windows 11 x64
- PowerShell 5.1+
- Developer Mode recommended (for long paths and symlinks)

## Required tooling

| Tool | Version | Verify | Purpose |
| ---- | ------- | ------ | ------- |
| Git | 2.40+ | `git --version` | Source control |
| Python | 3.12.10 | `python --version` | Sidecar backend |
| Node | 20+ / 24.18.0 validated | `node --version` | Vite + Tauri frontend |
| npm | 10+ | `npm --version` | Node packages |
| Rust | 1.96.1 | `rustc --version` | Tauri / Sentinel desktop |
| Tauri CLI | 2.11.4 | `npx tauri --version` | Bundling |
| WebView2 | latest | `reg query` HKLM... | WebView runtime |
| PyInstaller | 6.21.0 | `pyinstaller --version` | Sidecar bundle |

## Optional Windows tooling

- Visual Studio Build Tools / C++ workload (for Rust and PyInstaller)
- WiX Toolset (via Tauri bundle)
- NSIS (via Tauri bundle)

## Quick start

```powershell
git clone https://github.com/edgardo1997/AIVO.git C:\Dev\AIVO
cd C:\Dev\AIVO
Copy-Item .env.example .env
.\scripts\bootstrap-dev.ps1
.\scripts\verify-environment.ps1
```

## Common commands

```powershell
# Python gates
python -m uv run python -m pytest -m alpha_constitutional_gate -q
python -m uv run python -m pytest sidecar/tests/test_pdf_demo_plan.py sidecar/tests/test_pdf_demo_e2e.py sidecar/tests/test_pdf_demo_placeholders.py sidecar/tests/test_filesystem_pdf_tools.py -q

# Frontend
npm test
npm run build

# Rust
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings

# Sidecar bundle
pyinstaller sidecar.spec --noconfirm

# Tauri bundle (requires TAURI_SIGNING_PRIVATE_KEY for updater signing)
$env:TAURI_SIGNING_PRIVATE_KEY = "..."
npm run tauri:build
```

## Local model

Run the helper when a model URL and SHA-256 are provided:

```powershell
python scripts/download_local_model.py --url <URL> --sha256 <SHA256>
```

Sentinel must remain usable without a local model when running in cloud-free mode.

## Known issues

- OneDrive can cause file locks; use `C:\Dev\AIVO` or similar.
- `sidecar/dist/sidecar.exe` must be built before `cargo build` / Tauri bundle.
- `TAURI_SIGNING_PRIVATE_KEY` is required for signed updater artifacts.
- Real E2E tests require `SENTINEL_RUN_REAL_E2E=1`.
