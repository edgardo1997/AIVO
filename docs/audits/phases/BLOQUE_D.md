# Bloque D — FASE 4: Suite de pruebas

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `75a5833`
Commit final: `TBD` (post-cierre)

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 4 | **PARCIAL — unit, constitutional, frontend, Rust y smoke verdes; suite completa terminó con 6 fallos** | `python -m pytest -q` terminó con resumen completo. Los gates críticos y el pipeline canónico son verdes, pero persisten 6 fallos en tests de contract/release/executor/tool_gateway y 2.822 tests tenían marcadores inferidos en lugar de explícitos |

## 2. Evidencia ejecutada

### Subconjuntos verdes

| Comando | Resultado |
| ------- | --------- |
| `python -m pytest -m unit -q` | **231 passed, 0 failed** |
| `python -m pytest -m alpha_constitutional_gate -q` | **217 passed, 0 failed** |
| `python -m pytest tests/test_continuation_consumer.py -v` | **12 passed, 0 failed** |
| `python -m pytest tests/test_durable_consent_structure.py -v` | **5 passed, 0 failed** |
| `npm test` | **151 passed, 0 failed** |
| `npm run build` | OK (`dist/index.html` + assets) |
| `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` | OK |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | **5 passed, 0 failed** |
| `cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings` | OK |
| `smoke-sidecar` | OK, build_id presente |

### Suite completa

```powershell
cd sidecar && python -m pytest -q --durations=100
```

Resultado:

```text
6 failed, 3189 passed, 16 skipped, 31 warnings in 447.51s
```

Fallos:

```text
FAILED tests/test_executor.py::test_classify_command_destructive
FAILED tests/test_executor.py::test_destructive_patterns_endpoint
FAILED tests/test_release_contract.py::test_release_versions_are_consistent
FAILED tests/test_release_contract.py::test_updater_requires_signed_artifacts
FAILED tests/test_release_contract.py::test_windows_acl_hardening_is_packaged_and_documented
FAILED tests/test_tool_gateway.py::TestDelegation::test_executor_system_path_denied_by_guardian
```

## 3. Clasificación de markers

Se añadió inferencia automática en `sidecar/tests/conftest.py` para tests sin marker oficial, basada en ruta y nombre de archivo. Los markers oficiales fueron registrados en `sidecar/pyproject.toml`.

```text
3211 tests collected
0 legacy tras inferencia
```

La deuda es que ~1970 tests siguen clasificados por heurística en lugar de por markers explícitos.

## 4. Commits relevantes

- `0364dc1` — `fix(tests): encapsulate durable plan grant factory`
- `0bcfeb6` — `build: unify Build ID through build-sidecar.ps1`

## 5. Working tree final

```text
limpio
```

## 6. Siguiente bloque

**Bloque F-Cierre — Fases 2, 4, 5, 6, 14**.
