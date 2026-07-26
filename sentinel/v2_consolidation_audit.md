# SENTINEL V2 — AUDITORÍA DE CONSOLIDACIÓN FINAL

## Resumen

La inspección se realizó antes de modificar consumidores. Legacy no fue
inspeccionado como candidato de migración ni se conectó ningún runtime.

La fuente contractual central ya cubre autoridad, decisiones, evidencia,
health, readiness y auditoría. Las duplicaciones restantes se concentran en un
Health de Canary Observation, eventos de auditoría Canary, 19 snapshots de
métricas locales y presentadores de reporte por fase.

## Contratos y estados duplicados

- `canary_observation.health.CanaryHealthStatus` conserva estados locales
  `DISABLED`, `HEALTHY`, `WARNING`, `FAILED`.
- Los otros módulos Health migrados exportan aliases de `HealthStateV1`.
- `authorization_canary.audit.CanaryAuditEvent` es un enum de nombres de evento,
  no un registro completo; debe producir `AuditEventV1`.
- Los audit logs de activation, migration y observability ya almacenan
  `AuditEventV1`.
- Los resultados de decisión migrados heredan `DecisionResultV1`.
- No se encontraron `action_requested` ni `authority_explicit` en los paquetes
  consolidados.

## Métricas duplicadas

Se localizaron 19 snapshots locales en módulos V2. Son contadores internos por
fase y no deben convertirse en una segunda persistencia operacional.

Recomendación:

- conservar temporalmente contadores mínimos para compatibilidad;
- exportar eventos sanitizados hacia `operational_telemetry_hub` únicamente
  mediante adapters explícitos;
- impedir que snapshots locales almacenen eventos, payloads o decisiones
  ejecutables;
- usar `OperationalMetricSnapshotV1` como frontera persistente agregada.

## Reportes

Los reportes existentes son presentadores por fase. Pueden conservarse siempre
que reciban contratos/snapshots ya calculados y no creen decisiones, autoridad,
activación o acciones.

## Feature flags

| Flag | Módulo | Propósito | Estado recomendado |
|---|---|---|---|
| `OPERATIONAL_TELEMETRY_HUB_ENABLED` | telemetry hub | Persistencia consolidada | Mantener `False` |
| `PERSISTENT_CONTROL_BOUNDARY_ENABLED` | control boundary | Coordinación persistente | Mantener `False` |
| `V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED` | evidence storage | Storage legacy V2 | Mantener hasta migración explícita |
| `V2_OPERATIONAL_OBSERVABILITY_ENABLED` | observability | Observación local | Mantener hasta migración explícita |
| `CONTROLLED_RUNTIME_ACTIVATION_ENABLED` | controlled activation | Canary lógico | Mantener `False` |
| `V2_CANARY_ENABLED` | controlled activation | Canary lógico | Mantener `False` |
| `V2_AUTHORITY_MIGRATION_ENABLED` | authority migration | Simulación limitada | Mantener `False` |
| `FINAL_CONTROL_PLANE_READINESS_ENABLED` | final readiness | Evaluación humana | Mantener `False` |
| `V2_TRUST_EVALUATION_ENABLED` | trust evaluation | Confianza agregada | Mantener `False` |
| `ACTIVATION_GATEWAY_ENABLED` | activation gateway | Elegibilidad simulada | Mantener `False` |
| `APPLICATION_DISCOVERY_V2_ENABLED` | application discovery | Discovery shadow | Mantener desactivado |
| `AUTHORITY_SAFETY_LAYER_ENABLED` | authority safety | Seguridad persistente | Mantener `False` |
| `AUTHORIZATION_CANARY_ENABLED` | authorization canary | Grants simulados | Mantener desactivado |
| `CANARY_ENVIRONMENT_ENABLED` | canary environment | Entorno aislado | Mantener `False` |
| `CANARY_OBSERVATION_ENABLED` | canary observation | Observación pasiva | Mantener `False` |
| `CUTOVER_VALIDATION_ENABLED` | cutover validation | Evidencia previa | Mantener `False` |
| `DECISION_LONG_TERM_ENABLED` | long-term evaluation | Ventanas agregadas | Mantener `False` |
| `DECISION_SHADOW_VALIDATION_ENABLED` | decision shadow | Comparación pasiva | Mantener `False` |
| `POLICY_ENGINE_V2_SHADOW_ENABLED` | policy shadow | Política paralela | Mantener desactivado |
| `PROMOTION_VALIDATION_ENABLED` | promotion validation | Gates simulados | Mantener `False` |
| `RUNTIME_CANARY_ENABLED` | runtime canary | Pipeline paralelo | Mantener `False` |
| `RUNTIME_EQUIVALENCE_VALIDATION_ENABLED` | equivalence | Comparación sanitizada | Mantener `False` |
| `RUNTIME_REPLAY_VALIDATION_ENABLED` | replay validation | Replay sintético | Mantener `False` |
| `RUNTIME_TRIAL_ENABLED` | runtime trial | Escenarios simulados | Mantener `False` |
| `RUNTIME_V2_ROUTING_ENABLED` | controlled routing | Routing shadow | Mantener `False` |
| `V2_COMPARISON_ENABLED` | controlled routing | Comparación V2 | Mantener `False` |
| `STABILITY_VALIDATION_ENABLED` | stability validation | Estabilidad agregada | Mantener `False` |
| `V2_AUTHORITY_READINESS_ENABLED` | authority readiness | Readiness humana | Mantener `False` |

No se elimina ningún flag en esta fase.

## Riesgos

- Los snapshots locales todavía duplican forma, aunque no almacenamiento.
- Canary Observation necesita mapear `DISABLED` a `OBSERVING` y `FAILED` a
  `CRITICAL`.
- La coexistencia de Evidence Storage y Telemetry Hub requiere una estrategia
  posterior de migración y retención.
- Los reportes deben permanecer bajo pruebas AST para impedir lógica de
  decisión.
