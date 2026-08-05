# FASE 4 — ESTABILIZACIÓN DE PRUEBAS

Fecha: 2026-08-04
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit inicial: `ae94bf3`
Commit final: `36dcdb7`
Fuente de verdad: `https://github.com/edgardo1997/AIVO.git` (`main`)
Entorno: Python 3.12.10, Node v24.18.0, npm 11.16.0, Rust 1.96.1, Windows 11

---

## 1. Estado inicial

```text
git status --short  -> clean
git rev-parse HEAD  -> ae94bf3
pytest --collect-only -q -> 3177/3201 tests collected
```

---

## 2. Inventario de suites

Comando:

```text
python -m uv run python -m pytest --collect-only -q
```

Resultado:

```text
3177/3201 tests collected (24 deselected)
```

De los 3.177 tests, **2.812 no tenían marker oficial** y fueron etiquetados automáticamente como `legacy` por `conftest.py`.

No se encontraron benchmarks bajo `sidecar/tests` con nombre `test_*` en el discovery; la suite `performance` está excluida por `-m "not performance"`.

---

## 3. Aislamiento de datos

Se extendió `sidecar/tests/conftest.py` para redirigir *antes* de importar `main`:

- `SENTINEL_DB_PATH`
- `SENTINEL_DATA_DIR`
- `SENTINEL_CACHE_DIR`
- `SENTINEL_CONFIG_DIR`
- `SENTINEL_MODEL_DIR`
- `SENTINEL_PRODUCT_DIR`
- `LOCALAPPDATA`
- `APPDATA`
- `HOME`
- `USERPROFILE`

`TEMP` y `TMP` **no se redirigieron** porque `pytest` utiliza `C:\Users\...\AppData\Local\Temp\pytest-of-...` para `tmp_path` y el `PathGuardian` permite ese árbol a través de `%TEMP%`.

---

## 4. Aislamiento de bases

La fixture `isolated_test_database` ya existía. Se mantiene `db.db_path` en un directorio temporal y se compara contra `PRODUCTION_DB_PATH` para evitar contaminación. No se detectaron bases reales.

---

## 5. Puertos y procesos

- `conftest.py` configura `SENTINEL_PORT` vía fixture `clean_state` con puerto fijo `8765` para tests `TestClient`.
- Nuevo `scripts/smoke-sidecar.ps1` asigna un puerto libre dinámicamente para el sidecar compilado.
- Verifica que el proceso termina y el puerto queda liberado (con tolerancia a `TIME_WAIT`).

---

## 6. Markers

`pytest.ini` actualizado con:

- `legacy`
- `contract`
- `smoke`

`conftest.py` ahora:

- Recolecta tests sin marker.
- Les asigna `legacy` para mantener `--strict-markers` limpio.
- Emite `UserWarning` con la cuenta.
- Permite a CI fallar con `SENTINEL_FAIL_UNMARKED=1`.

Conteo actual de tests sin marker: **2.812**.

---

## 7. Benchmarks separados

El discovery normal excluye `performance` (`-m "not performance"`). No se encontraron archivos `test_*` de benchmark en `sidecar/tests`.

---

## 8. Tests lentos

Comando usado:

```text
python -m uv run python -m pytest -m unit -q -x --durations=15
```

Resultado parcial antes del primer fallo:

```text
1 failed, 791 passed, 573 deselected, 28 warnings in 69.93s
```

Tests más lentos observados:

| Test | Duración |
| ---- | -------: |
| `test_agent_delegate_returns_agent_info` | 6.66s |
| `test_chat_multiple_quick_actions` | 6.12s |
| `test_inventory_gateway_execute_only_in_authorized_files` | ~35s (auditoría AST) |

---

## 9. Bloqueos investigados

### Hang 1 — `test_execution_bypass_audit.py`

Causa: recorrido `rglob` sobre `sentinel/` y `sidecar/` después de builds, con archivos generados por PyInstaller.

Acción: filtrar `__pycache__`, `build`, `dist`, `node_modules`, `target`, `.git` y aumentar timeout a 120s para auditorías AST.

### Fallo 1 — `test_durable_plan_grant_factory_wired_only_through_broker_and_v1_router`

Causa: `sidecar/services/continuation_executor.py` referencia `request_plan_grant` y `approve_plan_grant` fuera de `ConfirmationBroker` y `v1/plans.py`.

Acción: **ninguna** en esta fase. Es una violación arquitectónica real que requiere decisión de diseño, no un parche silencioso.

---

## 10. Suite completa

`pytest` completa no se ejecutó por completo por duración. Subconjuntos:

| Subconjunto | Resultado |
| ----------- | --------- |
| `-m alpha_constitutional_gate` | **217 passed** |
| `-m unit -x` (parcial) | 791 passed, 1 failed |
| `sidecar/tests/test_execution_bypass_audit.py` | 11 passed |
| `npm test` | **151 passed** |
| `npm run build` | OK |
| `cargo test` | **5 passed** |
| `cargo clippy` | OK |
| `cargo fmt --check` | OK |

---

## 11. Assertions endurecidas

No se realizó refactors de assertions. Se priorizó aislamiento de datos, clasificación y smoke.

---

## 12. Mocks y fakes

No se auditó fakes. El `conftest.py` ya deshabilita `ModelRouter.check_health` y `windows_acl.ACL_ENABLED` para evitar side effects.

---

## 13. Contract tests

No se crearon nuevos contract tests. `docs/TESTING.md` define dónde deben ubicarse (`-m contract`).

---

## 14. Persistencia

La fixture `isolated_test_database` cubre aislación a nivel sesión. No se agregaron pruebas `create → close → reconstruct → validate`.

---

## 15. Concurrencia

No se agregaron pruebas de concurrencia. Marcador `stability` registrado para futuro trabajo.

---

## 16. Flakiness

No se ejecutaron repeticiones con `pytest-repeat`. No se identificaron flakes por falta de tiempo.

---

## 17. Sidecar smoke

Script: `scripts/smoke-sidecar.ps1`

Resultado:

```text
Health OK: {"status":"healthy","version":"1.0.0","runtime":"ready","database":"connected","gateway":"212 tools","router":"initialized",...}
SMOKE PASSED
```

Advertencia: el puerto puede permanecer en `TIME_WAIT` después del cierre. El binario responde correctamente.

---

## 18. Tauri smoke

No se automatizó. `cargo test` pasa y valida el contrato de health del sidecar.

---

## 19. Frontend

```text
npm test  -> 151 passed
npm run build -> OK
```

---

## 20. Rust

```text
cargo fmt --check  -> OK
cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings  -> OK
cargo test --locked --manifest-path src-tauri/Cargo.toml  -> 5 passed
```

---

## 21. Lint y análisis estático

- Python: `ruff` no se ejecutó. No se integró en CI.
- TypeScript: `npm test` y `npx tsc -b` implícito en `npm run build`.
- Rust: `cargo fmt` y `cargo clippy` pasan.

---

## 22. CI

- Workflow existente `.github/workflows/ci.yml` mantiene jobs con `pip` y `requirements.txt`.
- Nuevo `.github/workflows/repro.yml` propone un flujo Windows con `uv`, subconjuntos de pytest, Node 24, Rust y PyInstaller.
- No se ejecutó en GitHub; no se validó un runner real.

---

## 23. Required checks

No se configuraron checks requeridos. La instrucción para ello está documentada en `docs/TESTING.md`.

---

## 24. Cobertura

No se midió cobertura. No se establecieron thresholds.

---

## 25. Archivos modificados

- `pytest.ini`
- `sidecar/tests/conftest.py`
- `sidecar/tests/test_execution_bypass_audit.py`
- `src-tauri/src/lib.rs` (cargo fmt)
- `docs/TESTING.md` (nuevo)
- `scripts/smoke-sidecar.ps1` (nuevo)
- `.github/workflows/repro.yml` (nuevo)

---

## 26. Validaciones ejecutadas

| Comando | Resultado |
| ------- | --------- |
| `pytest --collect-only -q` | 3177 collected |
| `pytest -m alpha_constitutional_gate -q` | 217 passed |
| `pytest -m unit -q -x` | 791 passed, 1 failed |
| `pytest sidecar/tests/test_execution_bypass_audit.py` | 11 passed |
| `npm test` | 151 passed |
| `npm run build` | OK |
| `cargo test --locked` | 5 passed |
| `cargo clippy --locked` | OK |
| `cargo fmt --check` | OK |
| `pyinstaller sidecar.spec` | OK |
| `scripts/smoke-sidecar.ps1` | SMOKE PASSED |

---

## 27. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| pytest completo termina | **PARCIAL** (subconjuntos pasan) |
| Todos los tests oficiales pasan | **PARCIAL** (fallo arquitectónico conocido) |
| Cada test oficial pertenece a una categoría | **PARCIAL** (2.812 legacy) |
| Benchmarks fuera del discovery | **COMPLETADO** (`-m "not performance"`) |
| Tests no escriben datos personales | **COMPLETADO** (conftest redirige) |
| HOME/APPDATA/LOCALAPPDATA aislados | **COMPLETADO** |
| Bases de prueba temporales | **COMPLETADO** |
| Puertos aislados/dinámicos | **PARCIAL** (TestClient usa 8765; smoke es dinámico) |
| Procesos se cierran y puertos se liberan | **PARCIAL** (TIME_WAIT tolerado) |
| Tests más lentos identificados | **PARCIAL** (top 15 reportado) |
| Hangs investigados/corregidos | **PARCIAL** (1 AST timeout solucionado) |
| Assertions críticas reforzadas | **NO COMPLETADO** |
| Mocks críticos respetan contratos | **NO COMPLETADO** |
| Contract tests existen | **NO COMPLETADO** |
| Concurrencia real probada | **NO COMPLETADO** |
| Repetición/flakiness | **NO COMPLETADO** |
| cargo test pasa | **COMPLETADO** |
| cargo clippy pasa | **COMPLETADO** |
| cargo fmt --check pasa | **COMPLETADO** |
| npm test pasa | **COMPLETADO** |
| npm run build pasa | **COMPLETADO** |
| sidecar compilado pasa smoke | **COMPLETADO** |
| Tauri smoke mínimo | **NO COMPLETADO** |
| CI reproduce entorno limpio | **NO COMPLETADO** (workflow propuesto, no validado) |
| Required checks | **NO COMPLETADO** |

---

## 28. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | 2.812 tests sin marker; requieren clasificación manual o retag masivo |
| B-002 | `test_durable_consent_structure.py` falla por `continuation_executor.py` |
| B-003 | `unit` no termina en tiempo razonable en un job único |
| B-004 | Assertions, mocks y contract tests no auditados |
| B-005 | Tauri smoke no automatizado |
| B-006 | CI no ejecutado en runner limpio |

---

## 29. Cambios deliberadamente no realizados

- No se añadieron `xfail`/`skip` para ocultar fallos.
- No se reescribieron tests para ajustarse a una suite verde.
- No se restringió `test_execution_bypass_audit.py` con timeout corto sin causa.
- No se implementó lint/formatter Python nuevo.

---

## 30. Veredicto

**PARCIAL — infraestructura de aislamiento, markers y smoke avanzada.**

Se logró:

- Aislar data roots de los tests (`conftest.py`).
- Registrar markers oficiales y etiquetar tests faltantes.
- Resolver el hang del auditoría AST.
- Pasar gates constitucionales (217).
- Pasar frontend (151), Rust y formato.
- Smoke del sidecar compilado exitoso.

Pendiente:

- Clasificar 2.812 tests `legacy`.
- Resolver violación arquitectónica de `continuation_executor.py`.
- Completar contract tests, concurrencia, flakiness y CI real.
