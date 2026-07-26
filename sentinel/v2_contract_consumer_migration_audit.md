# SENTINEL V2 CONTRACT CONSUMER MIGRATION — AUDITORÍA PREVIA

## Alcance

Se inspeccionaron los 14 paquetes V2 indicados antes de modificar consumidores.
No se inspeccionó ni modificó el runtime Legacy.

## Hallazgos

### Autoridad y ejecución

- 13 modelos declaraban `authority=False` localmente.
- Cinco modelos ya declaraban también `execution_requested=False`.
- `v2_authority_migration.AuthorityDecision` usaba
  `authority_explicit=True`, aunque no ejecutaba acciones.
- Tres modelos usaban `action_requested=False`:
  `ObservationResultV1`, `TrustEvaluationResultV1` y
  `TrustRecommendationV1`.
- Varios resultados pasivos declaraban `authority=False` sin declarar
  `execution_requested=False`.

### Resultados y estados duplicados

- Se localizaron modelos propios de resultados en runtime trial, decision
  shadow, authority readiness, runtime equivalence, observability, trust,
  activation gateway, controlled activation y final readiness.
- Los paquetes mantienen vocabularios locales de health, readiness, recovery,
  activation y lifecycle. Son necesarios para compatibilidad, pero sus límites
  intermodulares no usan todavía los contratos centrales.
- Existen múltiples dataclasses locales de métricas, reports, audit events y
  gate results.

### Evidencia y auditoría

- Los eventos de auditoría de migration, activation gateway y controlled
  activation tienen formatos independientes.
- Correlation IDs, hashes, timestamps e integrity state no forman una envoltura
  común en todos los resultados.
- La nueva capa `contract_adapters` ofrece esa frontera sin importar módulos
  V2 ni runtime productivo.

### Seguridad

- No se encontraron imports directos desde estos paquetes hacia Executor,
  ToolGateway, Orchestrator, Planner Legacy, PolicyEngine Legacy o
  DecisionEngine Legacy.
- Las inconsistencias son contractuales; no constituyen por sí mismas una ruta
  de ejecución.

## Estrategia de migración

1. Hacer que todo resultado pasivo herede `DecisionResultV1`.
2. Eliminar campos `action_requested` y `authority_explicit`.
3. Conservar nombres de clases y campos funcionales para no romper consumidores.
4. Usar `contract_adapters` únicamente en fronteras de conversión.
5. Mantener enums y dataclasses internas hasta una fase posterior con adapters
   de compatibilidad explícitos.
6. Añadir una prueba AST global que impida reintroducir aliases o dependencias
   productivas.

## Riesgos previos

- Tests existentes pueden afirmar la presencia de aliases que ahora están
  prohibidos por el contrato central.
- La unificación completa de health/readiness/audit requiere migrar consumidores
  externos y no debe hacerse como reemplazo masivo en esta fase.
- Los hashes actuales no autentican criptográficamente al emisor.
