# Fase 15 — Shadow Runtime real

Fecha: 25 de julio de 2026.

## Resultado implementado

Se creó `sentinel/shadow_runtime_real`, una frontera opt-in que recibe:

1. un snapshot Legacy ya emitido, sanitizado e inmutable;
2. la solicitud contractual equivalente del pipeline V2;
3. evidencia humana explícita, cuando existe.

El observer crea copias profundas, ejecuta únicamente el pipeline V2 pasivo,
compara los resultados y registra una observación en el mismo Operational
Telemetry Hub utilizado por el pipeline.

## Comparaciones

- Fingerprint del plan.
- Resultado de política normalizado.
- Scope de autorización.
- Estado final.
- Campos Legacy no representados.

Las divergencias se clasifican como:

- `EXPECTED_DIFFERENCE`
- `INFORMATION_LOSS`
- `SECURITY_IMPROVEMENT`
- `V2_REGRESSION`
- `CRITICAL_DIVERGENCE`

Un bypass de una denegación Legacy o una ampliación de scope se clasifica como
crítico. La clasificación nunca modifica ni bloquea la decisión Legacy.

## Seguridad

- `SHADOW_RUNTIME_REAL_ENABLED = False`.
- No existe registro automático en Orchestrator o Runtime Legacy.
- No se importan Executor, ToolGateway productivo ni procesos del sistema.
- Los snapshots rechazan payloads, prompts y campos desconocidos.
- Todos los resultados mantienen `authority=False` y
  `execution_requested=False`.
- Un fallo V2 queda registrado como métrica y no se propaga al productor
  Legacy.

## Estabilidad

Las métricas agregadas alimentan `StabilityValidationEngine` sin retener
eventos, identidades o solicitudes. Se validó el procesamiento repetido y la
compatibilidad de una ventana de 72 horas mediante datos sintéticos.

El gate de observación prolongada **no puede considerarse cumplido todavía**:
requiere habilitación deliberada en un entorno canary y evidencia real obtenida
durante el periodo acordado.
