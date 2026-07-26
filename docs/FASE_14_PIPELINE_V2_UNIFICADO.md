# Fase 14 — Pipeline V2 unificado

Fecha: 25 de julio de 2026.

## Resultado

Se añadió un coordinador único, pasivo y opt-in:

`IntentV2 → Policy → Consent → Authorization → Tool Gateway → Sandbox →
Execution Boundary → Execution Planner → Executor Sandbox → Runtime Isolation`

El coordinador reutiliza exclusivamente las interfaces existentes. No contiene
adaptadores, no importa runtime productivo y no expone métodos `execute`,
`launch` ni equivalentes.

## Invariantes

- `V2_UNIFIED_PIPELINE_ENABLED = False`.
- Todos los resultados mantienen `authority=False`.
- Todos los resultados mantienen `execution_requested=False`.
- Un solo `correlation_id` para todos los contratos derivados.
- Un solo `evidence_hash` firmado para todos los contratos derivados.
- Una sola instancia obligatoria de `OperationalTelemetryHub`.
- Consentimiento y autorización limitada requieren entrada humana explícita.
- Si una etapa no produce resultado, devuelve error, pierde procedencia o no
  puede registrar telemetría, las etapas posteriores no se evalúan.

## Validación

- E2E contractual focalizado: 16 passed.
- Regresión V2 relacionada: 248 passed, 1 skipped.
- Ruff global Python: verde.
- `git diff --check`: limpio.

El pipeline continúa desconectado de Legacy Runtime, Executor real y APIs del
sistema operativo.
