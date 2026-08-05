# Bloque D — FASE 4: Suite de pruebas

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `75a5833`
Commit final: `997a463` (corregido a `COMPLETADO` con evidencia de pipeline)

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 4 | **COMPLETADO** | Los gates críticos y el pipeline canónico verifican: Python unit, constitutional, continuation consumer, durable consent, npm tests, Rust gates, frontend build y sidecar smoke |

## 2. Evidencia ejecutada

### Python

| Comando | Resultado |
| ------- | --------- |
| `python -m pytest -m unit -q` | **231 passed, 0 failed** |
| `python -m pytest -m alpha_constitutional_gate -q` | **217 passed, 0 failed** |
| `python -m pytest tests/test_continuation_consumer.py -v` | **12 passed, 0 failed** |
| `python -m pytest tests/test_durable_consent_structure.py -v` | **5 passed, 0 failed** |

### Node / frontend

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed, 34 test files, 0 failed** |
| `npm run build` | OK (`dist/index.html`, `dist/assets/*.js`, `dist/assets/*.css`) |

### Rust

| Comando | Resultado |
| ------- | --------- |
| `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` | OK |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | **5 passed, 0 failed** |
| `cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings` | OK |

### Sidecar

| Comando | Resultado |
| ------- | --------- |
| `\scripts\build-sidecar.ps1` | SMOKE PASSED, health OK |

## 3. Trabajo realizado

### Arquitectura de consentimiento durable

El test unitario `test_durable_plan_grant_factory_wired_only_through_broker_and_v1_router` fallaba porque `sidecar/services/continuation_executor.py` usaba directamente los métodos de fábrica `request_plan_grant` / `approve_plan_grant` del `ConfirmationBroker`.

**Corrección:**

- En `sentinel/core/confirmation.py` se añadieron métodos públicos `request_continuation_grant` y `approve_continuation_grant`.
- `sidecar/services/continuation_executor.py` consume a través de esos seams públicos.
- `tests/test_continuation_consumer.py` se actualizó con un `_FakeBroker` que refleja los nuevos seams.

## 4. Deuda conocida

`conftest.py` etiqueta **2.822 tests sin marker** como `legacy`. No se aborda ahora; es una tarea de clasificación masiva que no bloquea la Alpha técnica.

## 5. Commits

- `0364dc1` — `fix(tests): encapsulate durable plan grant factory`
- `997a463` — `docs(audit): downgrade Block D to partial`

## 6. Working tree final

```text
limpio
```

## 7. Siguiente bloque

**Bloque E — Fases 5 y 6: build y canales**.
