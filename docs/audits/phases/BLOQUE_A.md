# Bloque A — Fases 0, 1 y 2: Reproducibilidad

Fecha: 2026-08-05
Repositorio: `C:\Dev\AIVO`
Commit inicial: `7d5cbc4`
Commit actual: `cff16de`

## 1. Estado inicial

| Fase | Estado | Bloqueos |
| ---- | ------ | -------- |
| FASE 0 | no documentado | sin `docs/alpha/ALPHA_SCOPE.md` |
| FASE 1 | PARCIAL | B-001 (sidecar build), B-002 (`sentinel.local_model`), B-003 (`npm ci` limpio) |
| FASE 2 | RECHAZADO | `uv.lock`, `.python-version`, `rust-toolchain.toml`, bootstrap |

## 2. Trabajo realizado

### FASE 0 — Alcance Alpha

- Creado `docs/alpha/ALPHA_SCOPE.md`.
- Define funciones incluidas, excluidas, Feature Freeze y release gates.

### FASE 1 — Línea base reproducible

#### B-001: orden de build del sidecar

- Creado `scripts/build-sidecar.ps1`.
- Modificado `sidecar/sidecar.spec` para usar `SPECPATH` y rutas absolutas.
- Eliminado el prefijo `sidecar.` de los `hiddenimports` para que PyInstaller resuelva los paquetes del directorio del spec.
- El sidecar compila y pasa el smoke:

```text
Health OK: {"status":"healthy","version":"0.1.0-alpha.1",...}
SMOKE PASSED
```

#### B-002: `sentinel.local_model`

- Verificado: `sentinel/local_model/__init__.py` y `runtime.py` están versionados.
- `.gitignore` ya ignora solo binarios (`*.gguf`, `models/`, `runtime/`).
- **Resuelto**.

#### B-003: Node limpio

- `uv sync --frozen` funciona.
- `npm ci` funciona y no modifica `package-lock.json`.
- **Pendiente validar en clon limpio**.

## 3. Matriz de import de sidecar

| Import fallido | Archivo consumidor | Tipo de import | Causa raíz | Corrección |
| -------------- | ------------------ | -------------- | ---------- | ---------- |
| `from modules.sidecar_supervision import ...` | `sidecar/main.py` | absoluto top-level | `pathex=['.', '..']` en `sidecar.spec` dependía del CWD; al invocar `pyinstaller` desde la raíz, `.` era el repositorio y no `sidecar/` | Usar `SPECPATH` y `REPO_DIR` en `pathex` y rutas absolutas en `datas`/`Analysis` |
| `from modules import ...` | múltiples archivos sidecar | absoluto top-level | Los `hiddenimports` listaban `sidecar.modules.*` mientras el código importa `modules.*` | Eliminar prefijo `sidecar.` en `hiddenimports` |
| `from services import ...` | `sidecar/main.py` y servicios | absoluto top-level | Mismo pathex | Idem |
| `from routers import ...` | `sidecar/main.py` y routers | absoluto top-level | Mismo pathex | Idem |
| `from repositories import ...` | `sidecar/main.py` y tests | absoluto top-level | Mismo pathex | Idem |
| `import windows_acl` | `sidecar/main.py` | módulo top-level | Mismo pathex | Idem |

## 4. Pruebas

| Comando | Resultado |
| ------- | --------- |
| `uv sync --frozen` | OK |
| `npm ci` | OK (2 high vulnerabilities sin resolver) |
| `.\scripts\build-sidecar.ps1 -AllowDirty` | **SMOKE PASSED** |
| `python -m pytest -m alpha_constitutional_gate -q` | **215 passed, 2 failed** |

Fallos aislados observados (no bloquean B-001):

- `test_corrupt_lock_file_removed_not_killed`: termina un proceso huérfano real del entorno.
- `test_replaced_file_same_name_same_size_fails`: `ResourceIdentity` no calcula hash de contenido para contenidos de mismo tamaño.

## 5. Commits

- `df7e510` — `chore(env): add uv lockfiles`
- `76bae19` — `chore(build): add sidecar build script and Alpha scope doc`
- `cff16de` — `fix(packaging): resolve B-001 sidecar PyInstaller packaging`

## 6. Bloqueos restantes

- Validar FASE 1 en clon limpio (`C:\Dev\AIVO-repro-validation`).
- Resolver 2 tests de `alpha_constitutional_gate` fallidos.
- Alinear `rust-toolchain.toml` y validar `cargo` en clon limpio.

## 7. Siguiente paso

Crear clon limpio, ejecutar los gates oficiales y, si pasan, marcar FASE 1 como `COMPLETADO`. Luego continuar con el Bloque B: FASE 3.
