# Bloque F — FASE 14: Diagnóstico

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `45a5bbc`
Commit final: `5a93f24`

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 14 | **PARCIAL — build ID embebido** | El sidecar ahora reporta `build_id` en `/api/health` y `/api/info`; faltan exportación de diagnósticos, panel en GUI y logs estructurados con Build ID |

## 2. Trabajo realizado

### Build ID embebido en el sidecar

El sidecar ahora expone el identificador de build en sus endpoints de sistema:

- `sidecar/main.py` carga `_build_info` (módulo generado en build).
- `/api/health` incluye `build_id`.
- `/api/info` incluye `build_id`.

### Generación del build info

- `scripts/build-sidecar.ps1` escribe `sidecar/_build_info.py` antes de PyInstaller.
- `scripts/build-alpha.ps1` escribe `sidecar/_build_info.py` antes del bundle.
- `.gitignore` ignora el archivo generado.

### Evidencia

Smoke del sidecar:

```json
{"status":"healthy","version":"0.1.0-alpha.1","build_id":"internal-alpha-20260805-45a5bbc", ... }
```

### Commits

- `5a93f24` — `feat(build): embed build_id into sidecar runtime`

## 3. Deuda conocida

Fase 14 requiere además:

- endpoint `/api/support` para exportar logs, manifest y hashes;
- panel "Soporte / Acerca de" en la GUI con build ID, versión, commit;
- logs estructurados que incluyan build_id en cada línea;
- documentación de diagnóstico para usuarios de internal-alpha.

No se implementaron aún.

## 4. Working tree final

```text
git status --short:
 M src-tauri/Cargo.toml
 M src-tauri/gen/schemas/desktop-schema.json
 M src-tauri/gen/schemas/windows-schema.json
```

Diferencias debidas a generación de esquemas Tauri (Fase 2, pendiente).

## 5. Siguiente bloque

**Bloque G — Fases 7, 8, 9, 13** (GUI, flujos, rendimiento) o cerrar Fase 14 con soporte/exportación.
