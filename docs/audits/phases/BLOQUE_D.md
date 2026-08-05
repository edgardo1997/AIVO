# Bloque D — FASE 4: Suite de pruebas

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `0bcfeb6`
Commit final: `TBD` (post-cierre)

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 4 | **COMPLETADO** | `python -m pytest -q` finaliza con **0 fallos**. Los seis fallos previos fueron corregidos o reclasificados como contratos de canal alpha |

## 2. Evidencia ejecutada

### Subconjuntos verdes

| Comando | Resultado |
| ------- | --------- |
| `python -m pytest -m unit -q` | **231 passed** |
| `python -m pytest -m alpha_constitutional_gate -q` | **217 passed** |
| `python -m pytest tests/test_continuation_consumer.py -v` | **12 passed** |
| `python -m pytest tests/test_durable_consent_structure.py -v` | **5 passed** |
| `npm test` | **151 passed** |
| `npm run build` | OK (`dist/index.html` + assets) |
| `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` | OK |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | **5 passed** |
| `cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings` | OK |
| `smoke-sidecar` | OK, build_id presente |

### Suite completa

```powershell
cd sidecar && python -m pytest -q --durations=100
```

Resultado final:

```text
3195 passed, 16 skipped, 31 warnings in 490.31s
```

`exit code 0`, **0 tests fallidos**.

## 3. Correcciones de los seis fallos previos

| Test | Categoría | Corrección |
| ---- | --------- | ---------- |
| `test_executor.py::test_classify_command_destructive` | contrato de producción desactualizado (defaults vacíos) | Añadidas patterns destructivos por defecto en `sidecar/services/executor_service.py::_load_destructive_patterns()` |
| `test_executor.py::test_destructive_patterns_endpoint` | depende del anterior | Se corrige junto con el anterior |
| `test_tool_gateway.py::TestDelegation::test_executor_system_path_denied_by_guardian` | bug real de seguridad | Añadida validación de rutas del sistema en `ExecutorService.execute()` y `_is_system_path()` |
| `test_release_contract.py::test_release_versions_are_consistent` | contrato desactualizado (hardcoded `1.0.0`) | Ajustado a consistencia del canal `internal-alpha` (`0.1.0-alpha.1`) |
| `test_release_contract.py::test_updater_requires_signed_artifacts` | contrato desactualizado (canal alpha sin updater) | Ahora condicionado a si la versión es estable o prerelease |
| `test_release_contract.py::test_windows_acl_hardening_is_packaged_and_documented` | contrato desactualizado (nombre de módulo empaquetado) | Assert actualizado a `windows_acl` (presente en `sidecar.spec`) |

## 4. Clasificación de tests

Se añadió inferencia automática en `sidecar/tests/conftest.py` para tests sin marker oficial, basada en ruta/nombre de archivo. Los markers oficiales fueron registrados en `sidecar/pyproject.toml`.

```text
3211 tests collected
0 legacy tras inferencia
```

Aun así, la clasificación por heurística sigue siendo el mecanismo principal para tests sin marker explícito. Se documenta en Fase 4 / Bloque F-Final como deuda técnica a convertir en configuración por módulo.

## 5. Commits relevantes

- `0bcfeb6` — `build: unify Build ID through build-sidecar.ps1`
- `b89b929` — `docs(audit): update D/E and add F-Cierre report`

## 6. Working tree final

```text
limpio
```

## 7. Siguiente bloque

**Bloque F-Final — Cerrar Fases 4 y 14**. Fase 4 cerrada; Fase 14 sigue en progreso.
