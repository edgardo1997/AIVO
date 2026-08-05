# Bloque F-Cierre — Fases 2, 4, 5, 6, 14

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `0bcfeb6`
Commit final: `TBD`

## 1. Estado final

| Fase | Estado |
| ---- | ------ |
| FASE 2 | **COMPLETADO** |
| FASE 4 | **PARCIAL** |
| FASE 5 | **COMPLETADO** |
| FASE 6 | **COMPLETADO** |
| FASE 14 | **PARCIAL** |

## 2. Fase 2 — Determinismo

### Problema

`cargo build` y `tauri build` modificaban `src-tauri/Cargo.toml` y `src-tauri/gen/schemas/*.json` por diferencias de finales de línea (CRLF/LF) bajo `core.autocrlf=true`.

### Solución

- Añadido `.gitattributes` con:
  - `* text=auto eol=lf`
  - `*.ps1 text eol=crlf`
  - `src-tauri/Cargo.toml text eol=crlf`
  - `src-tauri/gen/schemas/*.json text eol=crlf`
- Normalización con `git add --renormalize`.
- Commits `911c858`.

### Validación

```powershell
cargo build --release
# git status limpio
cargo build --release
# git status limpio
```

## 3. Fase 5 y 6 — Build y canal

### Build ID único

- `build-alpha.ps1` genera el build ID.
- `build-sidecar.ps1` ahora acepta `-BuildId`.
- `build-alpha.ps1` invoca `build-sidecar.ps1` con ese ID.
- `_build_info.py` embebido en el sidecar.
- `/api/health` y `/api/info` devuelven `build_id`.
- El manifest y el sidecar comparten el mismo build ID.

### Build oficial limpio

```powershell
.\scripts\build-alpha.ps1 -Channel internal-alpha
```

Resultado:

```text
BUILD SUCCESS: internal-alpha-20260805-0bcfeb6
exit code 0
working tree limpio
```

### Hashes

```text
sidecar canónico: 87D45FD...75C6DD7
sidecar empaquetado: 87D45FD...75C6DD7  (coincide)
instalador NSIS: 8BA892...A12A3E868
```

## 4. Fase 4 — Suite

### Subconjuntos verdes

| Comando | Resultado |
| ------- | --------- |
| `pytest -m unit` | 231 passed |
| `pytest -m alpha_constitutional_gate` | 217 passed |
| `npm test` | 151 passed |
| `cargo test/clippy/fmt` | verde |

### Suite completa

```text
python -m pytest -q --durations=100
6 failed, 3189 passed, 16 skipped, 31 warnings
```

Fallos:

```text
test_executor.py::test_classify_command_destructive
test_executor.py::test_destructive_patterns_endpoint
test_release_contract.py::test_release_versions_are_consistent
test_release_contract.py::test_updater_requires_signed_artifacts
test_release_contract.py::test_windows_acl_hardening_is_packaged_and_documented
test_tool_gateway.py::TestDelegation::test_executor_system_path_denied_by_guardian
```

### Clasificación de markers

- `conftest.py` infiere markers por ruta/nombre para tests sin marker explícito.
- `pyproject.toml` registra markers oficiales adicionales (`contract`, `smoke`, `build`, `legacy`, `production`, `stress`, `chaos`).
- `3211` tests colectados, `0` legacy tras inferencia (pero ~1970 por heurística, no marcadores explícitos).

## 5. Fase 14 — Diagnóstico

### Completado

- Build ID embebido en `/api/health` y `/api/info`.
- Build ID único y consistente entre sidecar, frontend (via build) y manifest.

### Pendiente

- Pantalla de soporte y diagnóstico en GUI.
- Exportación de ZIP de diagnóstico.
- Servicio de redacción de secretos.
- Logs estructurados con `build_id`, `correlation_id` y taxonomía de errores.
- Niveles de restablecimiento.
- Pruebas de Fase 14.

## 6. Commits

- `911c858` — `.gitattributes`
- `0bcfeb6` — `build: unify Build ID through build-sidecar.ps1`

## 7. Bloqueos

- Los 6 fallos de `pytest` completos son pre-existing; bloquean declarar Fase 4 `COMPLETADO`.
- Fase 14 requiere trabajo de frontend y redacción no trivial.

## 8. Siguiente bloque

**Bloque G — Fases 7, 8, 9, 13** o completar Fase 14 primero.
