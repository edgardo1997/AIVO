# FASE 5 — PIPELINE DE BUILD

Fecha: 2026-08-04
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit inicial: `2db060d`
Commit final: `d854134`
Fuente de verdad: `https://github.com/edgardo1997/AIVO.git` (`main`)
Entorno: Python 3.12.10, Node v24.18.0, Rust 1.96.1, Windows 11 x64

---

## 1. Estado inicial

```text
git status --short -> clean
git rev-parse HEAD -> 2db060d
git branch --show-current -> main
```

---

## 2. Rutas de sidecar encontradas

| Ruta | Productor | Consumidor | Estado |
| ---- | --------- | ---------- | ------ |
| `sidecar/dist/sidecar.exe` | PyInstaller | Tauri bundle | CANÓNICA |
| `src-tauri/target/release/sentinel.exe` | cargo | N/A | binario Tauri |
| `src-tauri/target/release/bundle/nsis/*.exe` | Tauri | Instalador | generado |
| `C:\Users\<user>\.sentinel` | runtime | runtime | datos de usuario (NO build) |

Todas las referencias en `src-tauri/tauri.conf.json`, `src-tauri/build.rs`, `src-tauri/src/lib.rs`, `scripts/smoke-sidecar.ps1`, `docs` y CI apuntan a `sidecar/dist/sidecar.exe`.

---

## 3. Ruta canónica seleccionada

```text
<repo>/sidecar/dist/sidecar.exe
```

---

## 4. Cambios en PyInstaller

- `sidecar.spec`: eliminados hidden imports inexistentes:
  - `sidecar.services.triggers_service`
  - `sentinel.core.observability`
  - `sentinel.core.agent_registry`
  - `sentinel.advisory.scorer`

- PyInstaller ahora escribe directamente a `sidecar/dist/sidecar.exe`.

Build log final:

```text
INFO Build complete! The results are available in: ...\sidecar\dist
```

---

## 5. Hidden imports

Se eliminaron los `ERROR: Hidden import ... not found` que bloqueaban anteriormente. Solo quedan warnings no críticos:

```text
WARNING: Hidden import "pysqlite2" not found!
WARNING: Hidden import "MySQLdb" not found!
WARNING: Hidden import "psycopg2" not found!
```

Son dependencias opcionales de SQLAlchemy y no son necesarias para SQLite.

---

## 6. Limpieza controlada

`scripts/build-alpha.ps1` elimina únicamente antes de construir:

- `dist/`
- `sidecar/dist/`
- `sidecar/build/`
- `src-tauri/target/release/bundle/`
- `artifacts/`

No elimina datos, modelos, `.env`, vault, bases, código ni lockfiles.

---

## 7. Frontend build

```text
npm run build
```

Resultado:

```text
dist/index.html                   0.47 kB │ gzip:   0.30 kB
dist/assets/index-B0Pgjrk1.css   62.28 kB │ gzip:  11.16 kB
dist/assets/index-BGTZW5so.js   496.54 kB │ gzip: 132.81 kB
```

---

## 8. Sidecar build

```text
cd sidecar
python -m uv run pyinstaller sidecar.spec --noconfirm
```

Resultado:

```text
INFO Build complete! The results are available in: ...\sidecar\dist
```

Hash del sidecar canónico:

```text
SHA256(sidecar/dist/sidecar.exe) = EDD4F92A907F50F40C30F5D0AFAE5ED934C5FA7624C8F8CD9EC1A88A70252437
```

---

## 9. Sidecar smoke

```text
.\scripts\smoke-sidecar.ps1 -SidecarExe sidecar\dist\sidecar.exe
```

Resultado:

```text
Health OK: {"status":"healthy","version":"0.1.0-alpha.1",...}
SMOKE PASSED
```

---

## 10. Metadata

El script `build-alpha.ps1` genera `artifacts/alpha-manifest.json` con:

- product, version, channel
- commit, branch, build_id, timestamp
- platform, arch, python, node, rust
- sidecar_canonical, sidecar_sha256
- lista de artefactos con hash y tamaño

---

## 11. Versionado

- `package.json`: `0.1.0-alpha.1`
- `src-tauri/Cargo.toml`: `0.1.0-alpha.1`
- `src-tauri/tauri.conf.json`: `0.1.0-alpha.1`
- `pyproject.toml`: `0.1.0-alpha.1`
- `sidecar/main.py`: `version: "0.1.0-alpha.1"` (OpenAPI y `/api/info`)

Reemplazó el `1.0.0` hardcodeado.

---

## 12. Rust build

```text
cargo test --locked --manifest-path src-tauri/Cargo.toml  -> 5 passed
cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings  -> OK
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check  -> OK
cargo build --locked --release --manifest-path src-tauri/Cargo.toml  -> OK
```

---

## 13. Tauri build

Configuración ajustada:

- `bundle.createUpdaterArtifacts`: `false` (Alpha)
- `bundle.targets`: `["nsis"]` (MSI no soporta identificador `alpha.1`)

Comando:

```text
npm run tauri:build
```

Resultado:

```text
Built application at: ...\src-tauri\target\release\sentinel.exe
Running makensis to produce ...\bundle\nsis\Sentinel_0.1.0-alpha.1_x64-setup.exe
Finished 1 bundle
```

---

## 14. Inspección de bundle

Se extrajo el instalador NSIS silenciosamente a un directorio temporal:

```text
Sentinel_0.1.0-alpha.1_x64-setup.exe /S /D=C:\Users\...\sentinel-alpha-inspect
```

Archivos encontrados:

- `sentinel.exe`
- `sidecar/sidecar.exe`
- `uninstall.exe`

---

## 15. Comparación de hashes

| Artefacto | SHA-256 |
| --------- | ------- |
| Sidecar canónico (`sidecar/dist/sidecar.exe`) | `EDD4F92A907F50F40C30F5D0AFAE5ED934C5FA7624C8F8CD9EC1A88A70252437` |
| Sidecar empaquetado (`sentinel-alpha-inspect/sidecar/sidecar.exe`) | `EDD4F92A907F50F40C30F5D0AFAE5ED934C5FA7624C8F8CD9EC1A88A70252437` |

Resultado:

```text
MATCH
```

---

## 16. Firma y canal

- Canal: `alpha`
- Updater: deshabilitado (`createUpdaterArtifacts: false`)
- Authenticode: pendiente para release
- Manifesto: generado sin firma, con hashes SHA-256

---

## 17. Script canónico

`scripts/build-alpha.ps1` realiza la cadena completa:

```text
verify source
  ↓
clean
  ↓
npm ci + npm run build
  ↓
uv sync frozen
  ↓
PyInstaller
  ↓
smoke
  ↓
hash sidecar
  ↓
cargo test/clippy/fmt
  ↓
npm run tauri:build
  ↓
extract sidecar from installer
  ↓
hash comparison
  ↓
alpha-manifest.json
```

Falla ante cualquier error (`$ErrorActionPreference = "Stop"`).

---

## 18. Manifest de artefactos

Ejemplo generado por el script:

```json
{
  "product": "Sentinel",
  "version": "0.1.0-alpha.1",
  "channel": "alpha",
  "build_id": "alpha-20260805-d854134",
  "sidecar_sha256": "EDD4F92A907F50F40C30F5D0AFAE5ED934C5FA7624C8F8CD9EC1A88A70252437",
  "artifacts": [
    {
      "name": "Sentinel_0.1.0-alpha.1_x64-setup.exe",
      "sha256": "...",
      "size": 0
    }
  ]
}
```

---

## 19. CI

Workflows agregados:

- `.github/workflows/repro.yml`: gates por subconjuntos.
- `.github/workflows/build-alpha.yml`: build canónico completo.

No se ejecutaron en GitHub (entorno local).

---

## 20. Clon limpio

No se validó un clon limpio fuera de OneDrive en esta fase. Pendiente.

---

## 21. Archivos modificados

- `sidecar/main.py`
- `sidecar/sidecar.spec`
- `src-tauri/tauri.conf.json`
- `scripts/build-alpha.ps1` (nuevo)
- `docs/BUILD_AND_RELEASE.md` (nuevo)
- `.github/workflows/build-alpha.yml` (nuevo)

---

## 22. Tests ejecutados

| Comando | Resultado |
| ------- | --------- |
| `python -m uv run pyinstaller sidecar.spec --noconfirm` | exit 0 |
| `.\scripts\smoke-sidecar.ps1` | SMOKE PASSED |
| `npm run tauri:build` | exit 0 |
| extracción NSIS + hash compare | MATCH |
| `cargo test --locked` | 5 passed |
| `cargo clippy --locked` | OK |
| `cargo fmt --check` | OK |
| `npm run build` | OK |

---

## 23. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Existe ruta canónica | **COMPLETADO** |
| PyInstaller escribe en ruta canónica | **COMPLETADO** |
| Tauri consume ruta canónica | **COMPLETADO** |
| No hay rutas legacy activas | **COMPLETADO** |
| Limpieza controlada | **COMPLETADO** |
| Frontend build pasa | **COMPLETADO** |
| Sidecar build pasa | **COMPLETADO** |
| Sidecar smoke pasa | **COMPLETADO** |
| Hidden imports clasificados | **COMPLETADO** (faltantes eliminados) |
| Hidden imports activos incluidos | **COMPLETADO** |
| Hash del sidecar registrado | **COMPLETADO** |
| Rust test pasa | **COMPLETADO** |
| Rust clippy pasa | **COMPLETADO** |
| Rust release build pasa | **COMPLETADO** |
| Tauri build termina con exit 0 | **COMPLETADO** |
| Sidecar empaquetado fue inspeccionado | **COMPLETADO** |
| Hash fresco == hash empaquetado | **COMPLETADO** |
| Metadata incluye commit, build ID, canal, timestamp | **COMPLETADO** |
| Versiones coherentes | **COMPLETADO** |
| Versión Alpha reemplaza 1.0.0 | **COMPLETADO** |
| Build Alpha rechaza working tree dirty | **COMPLETADO** (default, `-AllowDirty` opt-in) |
| Manifest de artefactos fue generado | **COMPLETADO** |
| Build funciona en clon limpio | **PENDIENTE** |
| CI reproduce el pipeline | **PARCIAL** (workflow creado, no ejecutado en GitHub) |

---

## 24. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | Build en clon limpio no validado. |
| B-002 | CI no ejecutado en runner real. |
| B-003 | Authenticode y firma de updater pendientes para release. |
| B-004 | MSI target deshabilitado por identificador no numérico. |

---

## 25. Cambios no realizados

- No se agregaron funciones de producto.
- No se habilitó el updater para Alpha.
- No se firmó con Authenticode.
- No se borraron backups de `tauri.conf.json`.

---

## 26. Veredicto

**PARCIAL — pipeline canónico establecido y validado localmente.**

El build ya garantiza:

- una sola ruta canónica;
- PyInstaller sin errores de hidden imports activos;
- smoke del sidecar;
- hash SHA-256 del sidecar canónico;
- Tauri bundle con NSIS;
- extracción e inspección del sidecar empaquetado;
- igualdad de hashes `sidecar canónico == sidecar empaquetado`;
- manifest de artefactos;
- version `0.1.0-alpha.1` coherente.

Pendiente:

- validar en clon limpio;
- ejecutar CI en GitHub;
- firma y updater para release.
