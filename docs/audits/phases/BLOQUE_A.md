# Bloque A — Validación limpia: Fases 0, 1 y 2

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Clon de validación: `C:\Dev\AIVO-repro-validation`
Commit validado: `bb919c8a18b19bcfe23ffb56f7cb918af6ff3f8d`

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 0 | **COMPLETADO** | `docs/alpha/ALPHA_SCOPE.md` publicado en `main` |
| FASE 1 | **COMPLETADO** | Clon limpio reconstruye e inicia sidecar; pytest, npm y cargo gates pasan; solo quedan 2 bugs ya clasificados |
| FASE 2 | **PARCIAL** | Compilación, lockfiles y `.env.example` presentes; el build de Tauri modifica `src-tauri/gen/schemas/*.json`, dejando el working tree sucio hasta hacer `git checkout --` de los generados |

## 2. Validación limpia

### Preparación

```text
working tree limpio
rama main
HEAD local == origin/main  →  bb919c8a18b19bcfe23ffb56f7cb918af6ff3f8d
```

### Clon

```text
C:\Dev\AIVO-repro-validation
main
bb919c8a18b19bcfe23ffb56f7cb918af6ff3f8d
working tree limpio
```

### Artefactos heredados

| Ruta | Existe |
| ---- | ------ |
| `.venv` | `False` |
| `node_modules` | `False` |
| `sidecar\dist` | `False` |
| `sidecar\build` | `False` |
| `src-tauri\target` | `False` |
| `.env` | `False` |

### Cadena ejecutada

| Comando | Resultado |
| ------- | --------- |
| `uv sync --frozen` | OK (132 paquetes) |
| `npm ci` | OK (124 paquetes, 2 high vulnerabilities preexistentes) |
| `git status --short` (después de `npm ci`) | limpio |
| `.\scripts\build-sidecar.ps1` | **SMOKE PASSED** |
| `python -m pytest -m alpha_constitutional_gate -q` | **215 passed, 2 failed** |
| `npm test` | **151 passed, 34 test files** |
| `npm run build` | **OK** |
| `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` | **OK** |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | **5 passed, 0 failed** |
| `cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings` | **OK** |
| `cargo build --locked --release --manifest-path src-tauri/Cargo.toml` | **OK** |

### Sidecar smoke

```text
Health OK: {"status":"healthy","version":"0.1.0-alpha.1","runtime":"ready","database":"connected","gateway":"212 tools","router":"initialized","timestamp":"2026-08-04T23:16:32.239564-04:00"}
SMOKE PASSED
Sidecar hash: 3833a7596a0a7ca7f7a8cb6194938557c9b861f3d5f32744225022ab046c35f1
```

## 3. Estados de B-001, B-002, B-003

- **B-001** (`sidecar build`): `COMPLETADO` en clon limpio.
- **B-002** (`sentinel.local_model`): `COMPLETADO` — archivos fuente versionados.
- **B-003** (`npm ci` limpio): `COMPLETADO` — no modifica `package-lock.json`, `npm test` y `npm run build` pasan.

## 4. Fallos preservados para otros bloques

| Test | Bloque asignado | Causa observada |
| ---- | --------------- | --------------- |
| `test_corrupt_lock_file_removed_not_killed` | **Bloque C — Fase 10** | El cleanup de orfanos mata cualquier sidecar que no tenga lock válido, incluidos los del test |
| `test_replaced_file_same_name_same_size_fails` | **Bloque B — Fase 3** | `ResourceIdentity` no calcula hash de contenido cuando dos archivos tienen el mismo nombre y tamaño |

## 5. Problema Fase 2 detectado

El build de Tauri (`cargo build --release`) modifica:

- `src-tauri/gen/schemas/desktop-schema.json`
- `src-tauri/gen/schemas/windows-schema.json`

El working tree deja de estar limpio. Restaurar los archivos con `git checkout -- src-tauri/gen/schemas/*.json` devuelve el estado a limpio, pero esto indica que los esquemas generados deberían:

- estar en `.gitignore`; o
- ser reproducción determinista; o
- ser materializados fuera del repositorio.

Fase 2 permanece `PARCIAL` hasta resolverlo.

## 6. Working tree final del clon

```text
limpio (tras descartar cambios en esquemas generados)
```

## 7. Commits relevantes en `origin/main`

- `df7e510` — `chore(env): add uv lockfiles`
- `76bae19` — `chore(build): add sidecar build script and Alpha scope doc`
- `cff16de` — `fix(packaging): resolve B-001 sidecar PyInstaller packaging`
- `bb919c8` — `docs(audit): add Block A progress report`

## 8. Siguiente bloque

**Bloque B — Fase 3: constitucional**. Se inicia con la reproducción y corrección de `test_replaced_file_same_name_same_size_fails` en `sentinel/security/resource_identity.py`.
