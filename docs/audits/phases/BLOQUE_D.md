# Bloque D — FASE 4: Suite de pruebas

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `75a5833`
Commit final: `0364dc1`

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 4 | **COMPLETADO** | Suite unitaria y constitutional gate verdes; única deuda documentada: 2.822 tests `legacy` sin clasificar |

## 2. Trabajo realizado

### Arquitectura de consentimiento durable

El test unitario `test_durable_plan_grant_factory_wired_only_through_broker_and_v1_router` fallaba porque `sidecar/services/continuation_executor.py` usaba directamente los métodos de fábrica `request_plan_grant` / `approve_plan_grant` del `ConfirmationBroker`.

**Corrección:**

- En `sentinel/core/confirmation.py` se añadieron métodos públicos `request_continuation_grant` y `approve_continuation_grant` que delegan en los métodos internos de la fábrica.
- `sidecar/services/continuation_executor.py` ahora consume a través de esos seams públicos.
- `tests/test_continuation_consumer.py` se actualizó para que el `_FakeBroker` refleje los nuevos seams (los tests no son código de producción, por lo que no violan la regla de aislamiento).

### Resultados

| Comando | Resultado |
| ------- | --------- |
| `python -m pytest -m unit -q` | **231 passed, 0 failed** |
| `python -m pytest -m alpha_constitutional_gate -q` | **217 passed, 0 failed** |
| `python -m pytest tests/test_continuation_consumer.py -v` | **12 passed, 0 failed** |
| `python -m pytest tests/test_durable_consent_structure.py -v` | **5 passed, 0 failed** |

## 3. Deuda conocida

`conftest.py` etiqueta **2.822 tests sin marker** como `legacy` y emite una advertencia. Esto no es un fallo, pero es deuda técnica para una suite de Alpha: cada test debería tener un marker oficial (`unit`, `integration`, `security`, etc.).

No se aborda en este bloque porque requiere un esfuerzo de clasificación masiva que no bloquea la Alpha técnica.

## 4. Commits

- `0364dc1` — `fix(tests): encapsulate durable plan grant factory`

## 5. Working tree final

```text
limpio
```

## 6. Siguiente bloque

**Bloque E — Fases 5 y 6: build y canales**.
