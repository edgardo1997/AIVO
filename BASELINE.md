# Sentinel Pre-Alpha Baseline

This document identifies the reproducible pre-Alpha baseline for Sentinel.

## Identity

- **Version:** `0.1.0-alpha.1`
- **Tag:** `v0.1.0-alpha.1`
- **Branch canónica:** `main`
- **Branch de desarrollo previo:** `feature/sentinel-intelligence-migration`
- **Fecha:** 2026-08-04
- **Sistema operativo soportado:** Windows 10/11 x64
- **Localizaciones validadas:** `C:\Users\edgar\OneDrive\Documents\AIVO` (original), `C:\Dev\AIVO` (clon limpio de prueba)

## Requisitos del entorno

- Python 3.12.10
- Node 20.x
- Rust 1.86 (incluye cargo, clippy)
- Tauri CLI 2.11.4
- PyInstaller 6.21.0
- Microsoft Edge WebView2

## Comandos de verificación

```bash
# Sidecar — gates constitucionales
python -m pytest -m alpha_constitutional_gate -q

# Sidecar — demo PDF
python -m pytest sidecar/tests/test_pdf_demo_plan.py sidecar/tests/test_pdf_demo_e2e.py sidecar/tests/test_pdf_demo_placeholders.py sidecar/tests/test_filesystem_pdf_tools.py -q

# Frontend
npm test
npm run build

# Rust
cargo test --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
```

## Comandos de build

```bash
# Frontend
npm run build

# Sidecar
pyinstaller sidecar.spec --noconfirm

# Rust / Tauri
cargo build --release --manifest-path src-tauri/Cargo.toml
npm run tauri:build
```

## Artefactos esperados

- `dist/index.html` + assets
- `sidecar/dist/sidecar.exe`
- `src-tauri/target/release/sentinel.exe`
- `src-tauri/target/release/bundle/msi/Sentinel_0.1.0-alpha.1_x64_en-US.msi` *(nombre puede variar con versión)*
- `src-tauri/target/release/bundle/nsis/Sentinel_0.1.0-alpha.1_x64-setup.exe`

## Variables de entorno

Ver `.env.example`.

## Limitaciones conocidas

- El instalador requiere `TAURI_SIGNING_PRIVATE_KEY` para el updater.
- `npm run tauri:build` puede fallar en firma si la clave no está definida; los artefactos de bundle pueden generarse sin firma.
- `pyinstaller` emite advertencias de hidden imports residuales.
- El sidecar se empaqueta desde `sidecar/dist/sidecar.exe`; asegurar regenerarlo con `pyinstaller` antes de `tauri:build`.
- La GUI real no ha sido validada en entorno limpio; la cobertura actual es de tests automatizados.
- El build no incluye modelos locales; deben descargarse o configurarse vía `SENTINEL_OLLAMA_URL`.

## Notas de reproducibilidad

- El repositorio debe clonarse fuera de OneDrive para evitar locks y conflictos de sincronización.
- Las pruebas requieren un entorno con las dependencias de Python instaladas (`pip install -r requirements.txt` o equivalente).
- `npm install` es necesario para los tests y build de frontend.
