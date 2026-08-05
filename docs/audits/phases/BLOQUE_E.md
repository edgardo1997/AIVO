# Bloque E — Fases 5 y 6: Build y canales

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `0bcfeb6`
Commit final: `0bcfeb6`

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 5 | **COMPLETADO** | Build oficial `internal-alpha` limpio pasa; sidecar canónico, hash y bundle verificados |
| FASE 6 | **COMPLETADO** | Canal `internal-alpha` definido; updater deshabilitado; sin private key; manifest generado; Build ID único |
| FASE 2 | **COMPLETADO** | Build de Tauri ya no ensucia `src-tauri/Cargo.toml` ni `src-tauri/gen/schemas/*.json`; `git status` limpio tras build |

## 2. Build oficial limpio

Comando:

```powershell
.\scripts\build-alpha.ps1 -Channel internal-alpha
```

(no se usó `-AllowDirty`)

Resultado:

```text
BUILD SUCCESS: internal-alpha-20260805-0bcfeb6
exit code 0
git status --short: limpio
```

### Build ID único

- `buildId` se genera una vez en `build-alpha.ps1`.
- Se propaga a `sidecar/_build_info.py` vía `build-sidecar.ps1 -BuildId`.
- Sidecar `/api/health` y `/api/info` reportan `build_id`.
- Manifest de artefactos incluye el mismo `build_id`.

### Verificación de hashes

```text
sidecar canónico: 87D45FD38F2298882307CFD72F9188EDB68FD92D8014DB65F0A772E0E75C6DD7
sidecar empaquetado: 87D45FD38F2298882307CFD72F9188EDB68FD92D8014DB65F0A772E0E75C6DD7
instalador NSIS: 8BA892CDBC9515572C01A00BB183520C2C4B95FC96F6DBFA6EBE710A12A3E868
```

Los hashes del sidecar canónico y empaquetado coinciden.

### Canal `internal-alpha`

```text
channel = internal-alpha
version = 0.1.0-alpha.1
updater = disabled
Tauri private signing key = not required
Authenticode = optional/no requerido
hashes = required
manifest = required
working tree = clean
exit code final = 0
```

## 3. Determinismo Fase 2

- Se añadió `.gitattributes` con reglas de finales de línea.
- `src-tauri/Cargo.toml` y `src-tauri/gen/schemas/*.json` se normalizan a CRLF para coincidir con el generador Tauri en Windows.
- `cargo build --release` ejecutado dos veces; en ambas `git status --short` quedó vacío.

## 4. Commits

- `911c858` — `build: normalize Tauri generated files to CRLF via .gitattributes`
- `0bcfeb6` — `build: unify Build ID through build-sidecar.ps1`

## 5. Siguiente bloque

**Bloque F-Cierre — Fase 14: diagnóstico**.
