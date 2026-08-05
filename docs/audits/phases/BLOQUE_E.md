# Bloque E — Fases 5 y 6: Build y canales

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `997a463`
Commit final: `TBD`

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 5 | **COMPLETADO** | Pipeline canónico ejecutado exitosamente; sidecar canónico empaquetado, smoke pasa, Tauri bundle termina, hashes coinciden |
| FASE 6 | **COMPLETADO** | Canal `internal-alpha` definido; updater deshabilitado; no requiere private key; build termina exit 0; manifest generado |
| FASE 2 | **PARCIAL** | Build de Tauri modifica `src-tauri/Cargo.toml` y `src-tauri/gen/schemas/*.json` por conversión de finales de línea (CRLF vs LF); el árbol deja de estar limpio tras compilar |

## 2. Pipeline canónico

Comando ejecutado:

```powershell
.\scripts\build-alpha.ps1 -Channel internal-alpha -AllowDirty
```

**Resultado:** `BUILD SUCCESS: internal-alpha-20260805-997a463`

### Etapas

| Etapa | Entrada | Salida | Estado |
| ----- | ------- | ------ | ------ |
| `npm ci` | `package-lock.json` | `node_modules/` | OK |
| `npm run build` | `src/` | `dist/` | OK (`dist/index.html` generado) |
| `uv sync --frozen` | `uv.lock` | `.venv/` | OK (132 paquetes) |
| `pyinstaller sidecar.spec` | `sidecar/main.py` | `sidecar/dist/sidecar.exe` | OK |
| `smoke-sidecar` | `sidecar/dist/sidecar.exe` | health OK | **SMOKE PASSED** |
| `cargo test` | `src-tauri/` | test binary | **5 passed, 0 failed** |
| `cargo clippy` | `src-tauri/` | análisis | OK |
| `cargo fmt --check` | `src-tauri/` | — | OK |
| `tauri build` | `src-tauri/` + `dist/` + `sidecar/dist/` | `src-tauri/target/release/bundle/nsis/*.exe` | OK |
| verificación hash | `sidecar/dist/sidecar.exe` vs empaquetado | hash SHA-256 | **MATCH** |
| manifest | metadatos + hashes | `artifacts/internal-alpha/manifest.json` | OK |

### Hashes

```text
sidecar canónico: 511C58C6995437F35F624697CA87A4E4A0C9C6A91FA78ECC1D54E0581D8C8481
sidecar empaquetado: 511C58C6995437F35F624697CA87A4E4A0C9C6A91FA78ECC1D54E0581D8C8481
instalador NSIS: 45D1D3ACA024CC186384E581A60B995471500FDD9B5D8D10C7FC972F21F9D7E0
```

El empaquetado y el canónico coinciden.

## 3. Canal `internal-alpha`

Contrato verificado:

```text
channel = internal-alpha
version = 0.1.0-alpha.1
updater = disabled
Tauri private signing key = not required
Authenticode = optional/no requerido
hashes = required
manifest = required
working tree = clean al inicio (el build lo ensucia por esquemas generados)
exit code final = 0
```

- `tauri.conf.json`: `bundle.createUpdaterArtifacts: false`, `plugins.updater.endpoints: []`.
- `build-alpha.ps1`: rechaza `TAURI_SIGNING_PRIVATE_KEY` ausente para `external-alpha` y `stable`; `internal-alpha` no lo requiere.
- Manifest: `updater_enabled: false`, `tauri_signed: false`.

## 4. Ruta canónica del sidecar

```text
C:\Dev\AIVO\sidecar\dist\sidecar.exe
```

- PyInstaller produce directamente en esa ruta.
- `smoke-sidecar.ps1` la prueba.
- `tauri.conf.json` la empaqueta como `../sidecar/dist/sidecar.exe` → `sidecar/sidecar.exe`.
- No se encontraron rutas duplicadas ni `src-tauri/binaries/sidecar.exe` legacy.

## 5. Versionado

| Fuente | Valor |
| ------ | ------ |
| `package.json` | `0.1.0-alpha.1` |
| `src-tauri/tauri.conf.json` | `0.1.0-alpha.1` |
| `Cargo.toml` | `0.1.0-alpha.1` |
| sidecar manifest | `0.1.0-alpha.1` |

Todas coinciden.

## 6. Hidden imports de PyInstaller

Warnings persistentes, no críticos:

| Import | Tipo | Acción |
| ------ | ---- | ------ |
| `pysqlite2` | opcional | MySQL/SQLite alternativo no usado |
| `MySQLdb` | opcional | driver MySQL no usado |
| `psycopg2` | opcional | driver PostgreSQL no usado |

Son dependencias opcionales de SQLAlchemy para dialectos no utilizados en Windows/SQLite.

## 7. Fase 2: problema de esquemas Tauri

Tras `cargo build --release`, Git reporta modificaciones en:

- `src-tauri/Cargo.toml`
- `src-tauri/gen/schemas/desktop-schema.json`
- `src-tauri/gen/schemas/windows-schema.json`

La diferencia parece ser exclusivamente de finales de línea (CRLF generado por `tauri-build` vs LF en el índice). Fase 2 sigue `PARCIAL` hasta que se resuelva `.gitattributes` o se normalicen los archivos generados.

## 8. Manifest de artefactos

```text
artifacts/internal-alpha/manifest.json
```

Incluye:

```text
channel
build_id
version
commit
commit_short
timestamp_utc
dirty
tag
sidecar_sha256
frontend_dist
platform / arch / python / node / rust
updater_enabled
authenticode
tauri_signed
artifacts[] (path, sha256, size)
```

## 9. Commits

- `0364dc1` — `fix(tests): encapsulate durable plan grant factory`
- `997a463` — `docs(audit): downgrade Block D to partial`

## 10. Working tree final

```text
modificado por build de Tauri (src-tauri/Cargo.toml y gen/schemas/*.json)
```

## 11. Siguiente bloque

**Bloque F — Fase 14: diagnóstico**.
