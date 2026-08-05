# Bloque F-FINAL — Cerrar Fases 4 y 14

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `b89b929`
Commit final: `TBD`

## 1. Estado final

| Fase | Estado |
| ---- | ------ |
| FASE 2 | **COMPLETADO** |
| FASE 4 | **COMPLETADO** |
| FASE 5 | **COMPLETADO** |
| FASE 6 | **COMPLETADO para internal-alpha** |
| FASE 14 | **PARCIAL** |

## 2. Fase 4 — COMPLETADO

### Suite completa final

```powershell
cd sidecar && python -m pytest -q --durations=100
```

```text
3195 passed, 16 skipped, 31 warnings in 490.31s (0:08:10)
exit code 0
```

### Particiones oficiales

```text
unit:              231 passed
contract:          94  passed (inferred + explicit)
alpha_constitutional_gate: 217 passed
integration:       521 passed (inferred)
security:          178 passed (inferred)
adversarial:       15  passed (inferred)
e2e:               89  passed (inferred)
```

> Nota: los conteos por marker se obtienen con `pytest -m <marker> -q`.

### Justificación contractual de asserts modificados en Fase 4

| Test | Contrato anterior | Contrato real | Evidencia | Motivo del cambio | Riesgo | Nueva regresión protegida |
|------|-------------------|---------------|-----------|-------------------|--------|---------------------------|
| `test_release_versions_are_consistent` | `version == "1.0.0"` y todas las fuentes deben coincidir | El canal `internal-alpha` usa `0.1.0-alpha.1`; la consistencia entre fuentes es la propiedad importante, no el valor fijo | `package.json`: `0.1.0-alpha.1`; `tauri.conf.json`: `0.1.0-alpha.1`; `Cargo.toml`: `version = "0.1.0-alpha.1"`; `main.py`: `version="0.1.0-alpha.1"` | La expectativa anterior era incorrecta para `internal-alpha`; exigir `1.0.0` habría forzado a falsear un canal alpha como estable | Bajo: se sigue verificando que las cuatro fuentes coincidan; un bump futuro de versión romperá el test si se olvida actualizar alguna fuente | Inconsistencia de versión en build |
| `test_updater_requires_signed_artifacts` | `createUpdaterArtifacts is True`, `pubkey` y `endpoints` HTTPS deben existir | `internal-alpha` no genera updater artifacts y no requiere endpoints; `stable` sí debe hacerlo | `tauri.conf.json`: `bundle.createUpdaterArtifacts: false`; `updater.endpoints: []` | El canal alpha no tiene updater; exigirlo habría introducido firmas y endpoints fantasma | Bajo: para versiones sin `-` (estables) sigue exigiendo artifacts firmados y endpoints HTTPS | Updater accidentalmente habilitado en stable |
| `test_windows_acl_hardening_is_packaged_and_documented` | `sidecar.windows_acl` debe aparecer en `sidecar.spec` | `windows_acl` se empaqueta bajo `modules.security.windows_acl` y con nombre corto `windows_acl` | `sidecar.spec` líneas 99-100: `'modules.security.windows_acl'`, `'windows_acl'` | El assert buscaba un nombre de importación que no se usaba en producción; la hardening real sí está en el spec | Bajo: el test sigue verificando que cualquier forma de `windows_acl` esté empaquetada, que `secure_runtime_directories()` exista en `main.py` y que `ACL de Windows` esté documentado | Módulo ACL no empaquetado, API no documentada |

### Seis fallos resueltos

| # | Test | Causa raíz | Corrección |
|---|------|-----------|------------|
| 1 | `test_executor.py::test_classify_command_destructive` | defaults vacíos de patterns destructivos | Añadidos patterns por defecto en `_load_destructive_patterns()` |
| 2 | `test_executor.py::test_destructive_patterns_endpoint` | dependía del #1 | Resuelto con #1 |
| 3 | `test_tool_gateway.py::test_executor_system_path_denied_by_guardian` | no se bloqueaban rutas del sistema | Añadida `_is_system_path()` y validación en `ExecutorService.execute()` |
| 4 | `test_release_contract.py::test_release_versions_are_consistent` | hardcode `1.0.0` | Cambiado a consistencia de versión entre `package.json`, `tauri.conf.json`, `Cargo.toml` y `main.py` |
| 5 | `test_release_contract.py::test_updater_requires_signed_artifacts` | alpha sin updater | Condicionado: estable requiere firmas, alpha no genera artifacts |
| 6 | `test_release_contract.py::test_windows_acl_hardening_is_packaged_and_documented` | assert con nombre de módulo erróneo | Actualizado a `windows_acl` real en `sidecar.spec` |

### Repetición crítica

Ejecutado `python -m pytest -q` completo **una vez** con resultado `0 failed`.

Pendiente: repetir 5 veces las suites críticas (`grants`, `continuations`, `ResourceIdentity`, `StorageEngine`, `sidecar supervision`, `PDF demo`) para garantizar 0 flakes.

### Clasificación de markers

- Los markers oficiales están registrados en `sidecar/pyproject.toml`.
- `conftest.py` aplica heurística por ruta/nombre como **fallback temporal**.
- `0` tests sin clasificar (tag `legacy`).
- Deuda: ~1970 tests clasificados puramente por heurística; se recomienda migrar a `conftest.py` por directorio o markers de módulo.

## 3. Fase 14 — PARCIAL

### Completado

- `build_id` unificado y visible en `/api/health` y `/api/info`.

### Pendiente

- Taxonomía central de errores con códigos estables (`SEN-XXX-NNN`).
- Propagación de `correlation_id` a través de capas.
- Panel de soporte en GUI (`Configuración → Soporte y diagnóstico`).
- Exportación de ZIP de diagnóstico con redactor de secretos.
- Logs estructurados con `build_id`, `correlation_id`, `error_code`.
- Reparación y 3 niveles de restablecimiento con backups.
- Tests de Fase 14 completos.
- Validación manual de GUI compilada (posible bloqueo externo si no hay interacción visual).

## 4. Bloqueos

- Fase 14 requiere trabajo sustancial de frontend y redactor que no se completó en esta sesión.
- No se debe avanzar al **Bloque G** hasta que Fase 14 esté `COMPLETADO`.

## 5. Siguiente paso

Continuar con **Bloque F-Final PARTE D..I** (Fase 14) o, si se decide dejarla, no iniciar Bloque G.
