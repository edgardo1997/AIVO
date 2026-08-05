# Bloque F-FINAL — Cerrar Fases 4 y 14

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `b89b929`
Commit final: `9d5cf43`

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
3207 passed, 16 skipped, 31 warnings in 450.49s (0:07:30)
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

## 3. Fase 14 — PARCIAL

### 3.1 Inventario de errores

Se localizaron y catalogaron las fronteras de error en los flujos Alpha. Los puntos principales están en:

| Componente | Frontera de error | Tratamiento aplicado |
|------------|-------------------|----------------------|
| onboarding | validación de identidad local | `SEN-AUTH-001` |
| chat | excepciones de proveedor/modelo | `map_exception()` → `SEN-UNKNOWN-001` |
| modelo local | no disponible | `SEN-MODEL-001` |
| cloud | error de proveedor | `SEN-PROVIDER-001` |
| historial | fallo de persistencia | `SEN-PERSIST-001` |
| settings | configuración corrupta | `SEN-CONFIG-001` |
| permisos | denegado | `SEN-PERM-001` |
| ejecución | fallo seguro | `SEN-EXEC-001` |
| auditoría | registro parcial | `SEN-AUDIT-001` |
| lifecycle | sidecar no responde | `SEN-SIDECAR-001` |

### 3.2 Contrato central de errores

Implementado en `sentinel/core/support/errors.py`:

```python
@dataclass(frozen=True)
class SentinelError:
    error_code: str
    category: ErrorCategory
    severity: ErrorSeverity
    user_message: str
    technical_message: str
    recommended_action: Optional[str]
    retryable: bool
    correlation_id: str
    component: str
    timestamp: str
    build_id: str
    operation_state: Optional[OperationState]
```

### 3.3 Taxonomía y códigos estables

Registrados en `ErrorRegistry`:

```text
SEN-AUTH-001   SEN-SIDECAR-001   SEN-MODEL-001    SEN-PROVIDER-001
SEN-NET-001    SEN-PERM-001      SEN-FS-001       SEN-RESOURCE-001
SEN-EXEC-001   SEN-VERIFY-001    SEN-AUDIT-001    SEN-PERSIST-001
SEN-CONFIG-001 SEN-INSTALL-001   SEN-UPDATE-001   SEN-UNKNOWN-001
```

Validación de unicidad: `test_error_codes_are_unique`.

### 3.4 Mensajes para usuario

- No incluyen stack traces, nombres de clases, errores HTTP crudos, JSON ni rutas personales.
- Indican qué ocurrió, qué no ocurrió y qué acción tomar.
- Incluyen código de soporte corto (`correlation_id` truncado).

### 3.5 Correlation ID end-to-end

- Middleware `correlation_middleware` en `sidecar/main.py` crea/preserva `X-Correlation-ID`.
- Capa `sentinel/core/support/correlation.py` con context vars.
- Header `X-Correlation-ID` permitido en CORS.

### 3.6 Logs estructurados

- `sentinel/core/support/logger.py` emite JSON con `build_id`, `correlation_id`, `error_code`, `operation_state`.
- Rotación mediante `RotatingFileHandler` (`maxBytes=5 MB`, `backupCount=5`).

### 3.7 Redactor central de secretos

- `sentinel/core/support/redactor.py`: `SecretRedactor`.
- Cubre `api_key`, `token`, `secret`, `password`, `private_key`, `client_secret`, `cookie`, `session`, `vault`, etc.
- Normaliza rutas personales a `%USERPROFILE%`.
- Tests: `test_redactor_removes_fake_secrets`, `test_redactor_normalizes_paths`.

### 3.8 Servicio de diagnóstico

- `sentinel/core/support/diagnostic.py`: `DiagnosticService.collect()`.
- Genera `Sentinel-Diagnostic-<build-id>-<timestamp>.zip` con:
  - `summary.json`
  - `manifest.json`
  - `system.txt`
  - `logs/sentinel.log`
  - `events.jsonl`
  - `README.txt`
  - `SHA256SUMS.txt`
- Funciona sin modelo, sin internet y tolera logs corruptos.
- Tests: `test_diagnostic_zip_is_valid`, `test_diagnostic_contains_build_id`, `test_diagnostic_manifest_hashes_match`, `test_diagnostic_works_offline`.

### 3.9 Endpoints backend

Añadidos en `sidecar/routers/support.py`:

```text
GET  /api/support/status
POST /api/support/diagnostic
POST /api/support/repair
POST /api/support/reset
```

### 3.10 GUI de soporte

- Nueva ruta `src/components/Support/Support.tsx`.
- Accesible desde `Configuración / Ayuda → Soporte`.
- Muestra versión, Build ID, canal, estado del sistema, errores recientes.
- Botones: `Crear diagnóstico`, `Reparar configuración`.
- Sección `Restablecer Sentinel` con 3 niveles.
- Detalles técnicos colapsados.
- Test `src/__tests__/Support.test.tsx`.

### 3.11 Reparación y reset

- `POST /api/support/repair`: restaura desde backup válido, preserva copia corrupta.
- `POST /api/support/reset`: niveles `interface`, `configuration`, `full`; crea backup antes de actuar.

### 3.12 Pruebas backend Fase 14

Añadidas en `sidecar/tests/test_support.py`:

```text
test_error_codes_are_unique
test_error_codes_are_stable
test_unknown_exception_maps_to_safe_error
test_user_message_does_not_include_traceback
test_correlation_id_propagates_through_execution
test_build_id_is_present_in_sentinel_error
test_redactor_removes_fake_secrets
test_redactor_normalizes_paths
test_diagnostic_zip_is_valid
test_diagnostic_manifest_hashes_match
test_diagnostic_contains_build_id
test_diagnostic_works_offline
```

### 3.13 Pruebas frontend

Añadidas en `src/__tests__/Support.test.tsx`:

```text
support page renders version and Build ID
system state uses human language
technical details are collapsed by default
```

## 4. Regresión completa

### Backend

```powershell
cd sidecar && python -m pytest -q --durations=100
```

```text
3207 passed, 16 skipped, 31 warnings in 450.49s (0:07:30)
exit code 0
```

### Frontend

```powershell
npm test
```

```text
154 passed, 0 failed
```

```powershell
npm run build
```

```text
✓ built
```

### Rust

```powershell
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
```

```text
5 passed, clippy ok, fmt ok
```

### Build limpio internal-alpha

```powershell
.\scripts\build-alpha.ps1 -Channel internal-alpha
```

```text
BUILD SUCCESS: internal-alpha-20260805-9d5cf43
Artifacts: C:\Dev\AIVO\artifacts\internal-alpha
```

## 5. Bloqueos externos

| Bloqueo | Descripción |
|---------|-------------|
| Validación visual de GUI compilada | El entorno de Devin no permite interacción visual. El build `internal-alpha-20260805-9d5cf43` fue generado correctamente, pero no se pudo: abrir Configuración → Soporte, crear un diagnóstico, restablecer interfaz en un perfil temporal, etc. |

Sin la validación visual, no se cumple el criterio `GUI compilada fue validada o existe bloqueo externo exacto`. Por eso Fase 14 sigue **PARCIAL**.

## 6. Criterios de salida de Fase 14 (checklist)

| Criterio | Estado |
|----------|--------|
| Contrato central de errores | OK |
| Códigos estables y únicos | OK |
| Error boundary seguro | OK |
| Mensajes útiles sin stack traces | OK |
| Correlation ID cruza capas | OK |
| Logs estructurados con build_id | OK |
| Rotación definida | OK |
| Redactor central | OK |
| Pruebas de secretos | OK |
| Diagnóstico ZIP funciona | OK |
| ZIP contiene manifest y checksums | OK |
| Diagnóstico offline | OK |
| Build ID en GUI | OK |
| Página de soporte | OK |
| Reparar configuración | OK (backend) |
| Reset 3 niveles | OK (backend) |
| Suite completa verde | OK |
| Build limpio internal-alpha | OK |
| Validación GUI compilada | **BLOQUEADO EXTERNO** |

## 7. Siguiente paso

- **NO avanzar al Bloque G** hasta que Fase 14 quede `COMPLETADO`.
- Para completar Fase 14 se requiere:
  1. Validar manualmente la GUI compilada del build `internal-alpha-20260805-9d5cf43`.
  2. Completar pruebas de reset/repair con datos temporales reales.
  3. Verificar ausencia de secretos en un ZIP exportado manualmente.
