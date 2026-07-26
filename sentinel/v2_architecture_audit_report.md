# SENTINEL V2 ARCHITECTURE CONSOLIDATION AUDIT

## Resumen ejecutivo

La arquitectura V2 auditada está físicamente aislada del runtime productivo: no se
encontraron imports hacia Executor, ToolGateway, Orchestrator, Planner Legacy,
PolicyEngine Legacy o DecisionEngine Legacy, ni llamadas para iniciar procesos.
Legacy continúa siendo la única autoridad productiva.

El conjunto revisado contiene 14 paquetes, 121 archivos Python y aproximadamente
4.959 líneas. La cobertura asociada incluye 61 archivos de prueba y unas 3.639
líneas. La separación por fases facilitó el aislamiento, pero produjo una
arquitectura fragmentada: hay múltiples vocabularios para autoridad, health,
recovery, readiness, auditoría, métricas y feature flags.

La conclusión es **no consolidado para integración**. No existe un bypass
productivo confirmado, pero antes de conectar cualquier control plane deben
unificarse los contratos, vincularse la persistencia con routing/idempotencia y
reemplazarse señales booleanas o strings por evidencia tipada y verificable.

## Alcance auditado

- `canary_environment`
- `runtime_trial`
- `decision_shadow_validation`
- `decision_long_term_evaluation`
- `v2_authority_readiness`
- `v2_authority_migration`
- `authority_safety_layer`
- `runtime_equivalence_validation`
- `activation_gateway`
- `controlled_runtime_activation`
- `v2_operational_observability`
- `v2_operational_evidence_storage`
- `v2_trust_evaluation`
- `final_control_plane_readiness`

## Arquitectura actual

La arquitectura forma seis grupos lógicos:

1. **Simulación y canary:** `canary_environment`, `runtime_trial`.
2. **Comparación y observación:** `decision_shadow_validation`,
   `decision_long_term_evaluation`, `runtime_equivalence_validation`,
   `v2_operational_observability`.
3. **Readiness y confianza:** `v2_authority_readiness`,
   `v2_trust_evaluation`, `final_control_plane_readiness`.
4. **Selección lógica:** `v2_authority_migration`, `activation_gateway`,
   `controlled_runtime_activation`.
5. **Persistencia:** `authority_safety_layer`,
   `v2_operational_evidence_storage`.
6. **Presentación:** reportes y métricas independientes en casi todos los
   paquetes.

Solo se detectaron dos dependencias entre paquetes auditados:

- `runtime_trial` depende de `canary_environment` y contratos V2.
- `decision_long_term_evaluation` depende de la clasificación de
  `decision_shadow_validation`.

No se detectaron ciclos estáticos en el grafo actual. El uso repetido de exports
lazy en `__init__.py` reduce el riesgo de ciclos de inicialización, aunque también
oculta dependencias hasta tiempo de ejecución.

## Problemas encontrados

### HIGH — La invariante de autoridad no es uniforme

`v2_authority_migration.router.AuthorityDecision` declara
`authority_explicit=True` en lugar de `authority=False`. Además:

- `RuntimeTrialResult`, `RuntimeEquivalenceResultV1`,
  `AuthorityReadinessResultV1` y `DecisionShadowResultV1` no exponen
  `execution_requested`.
- Observabilidad y confianza usan `action_requested=False`, que no es el mismo
  contrato.
- Varios resultados, reports y snapshots no declaran ninguna marca de autoridad.

No hay ejecución real conectada, pero no puede verificarse la regla global
“toda decisión es no autoritativa” con una sola interfaz.

**Recomendación:** crear una base contractual común
`NonAuthoritativeDecisionV1` con `authority: Literal[False]` y
`execution_requested: Literal[False]`. Prohibir aliases semánticos.

### HIGH — Routing e idempotencia persistente están desacoplados

`v2_authority_migration` y `controlled_runtime_activation` conservan decisiones,
correlaciones y fallbacks en diccionarios o sets en memoria. La persistencia de
`authority_safety_layer` no está conectada a esos routers.

Después de reiniciar el proceso se pierde:

- la asignación canary determinista ya emitida como objeto;
- el registro de fallback manejado;
- la protección local contra repetición;
- el estado de métricas y auditoría.

Esto no afecta al runtime actual porque no existe integración, pero sería un
bloqueo de seguridad para cualquier canary con efectos.

**Recomendación:** antes de integrar, exigir una única transacción persistente
que reserve correlación, decisión, evidence hash y estado terminal. El router no
debe emitir una selección V2 si esa reserva no fue confirmada.

### HIGH — Señales finales no tienen procedencia verificable

`final_control_plane_readiness` agrega strings, booleanos, tasas y contadores
proporcionados por el caller. No valida que provengan de los módulos declarados,
que pertenezcan a la misma ventana temporal o que compartan correlation/evidence
hash.

Un caller podría declarar manualmente readiness, safety, equivalence y trust
como saludables y obtener un resultado de revisión alta.

**Recomendación:** usar un `EvidenceSignal` versionado con emisor, versión,
ventana, correlation hash, payload hash, timestamp, expiración e integrity
proof. El agregador debe rechazar señales mezcladas, expiradas o sin origen.

### HIGH — Integridad operacional no es autenticidad

`v2_operational_evidence_storage` usa SHA-256 canónico. Detecta corrupción
accidental, pero un actor con acceso de escritura puede modificar datos y
recalcular el hash. La base tampoco cifra evidencia ni encadena registros.

**Recomendación:** introducir HMAC o firma con rotación de claves, encadenamiento
de hashes, identidad del emisor y verificación de continuidad. Mantener SHA-256
solo como checksum interno.

### MEDIUM — Dos almacenes SQLite sin modelo transaccional común

`authority_safety_layer` y `v2_operational_evidence_storage` tienen conexiones,
schemas, recovery e integrity independientes. Una decisión podría quedar
`COMMITTED` en safety y faltar en evidence, o viceversa.

También existen vocabularios incompatibles:

- `SAFE_RECOVERY`, `RECOVERY_REQUIRED`, `BLOCKED_RECOVERY`;
- `RECOVERY_OK`, `RECOVERY_REQUIRED`, `RECOVERY_BLOCKED`.

**Recomendación:** compartir un storage envelope y una unidad de trabajo, aunque
las tablas sigan separadas. Normalizar un único `RecoveryStatusV1`.

### MEDIUM — Responsabilidades solapadas en selección y activación

Tres paquetes toman decisiones similares:

- `v2_authority_migration` selecciona `LEGACY_AUTHORITY`, `V2_AUTHORITY` o
  fallback.
- `activation_gateway` declara elegibilidad shadow/canary.
- `controlled_runtime_activation` selecciona Legacy o V2 canary.

Cada uno repite scope, readiness, safety, rollback, porcentaje, expiración y
fallback con nombres distintos. No hay contrato que fuerce el orden
Gateway → Migration Policy → Activation Router.

**Recomendación:** conservar tres responsabilidades, pero definir interfaces
únicas:

1. gateway produce elegibilidad;
2. migration policy produce autorización de routing no ejecutable;
3. router consume esa autorización de una sola vez.

### MEDIUM — Vocabularios duplicados e incompatibles

Se encontraron 30 enums y 17 constantes de flags/porcentajes. Existen estados
paralelos para:

- health: `HEALTHY`, `WARNING`, `UNSTABLE`, `DEGRADED`, `FAILED`, `CRITICAL`;
- readiness: `READY_FOR_REVIEW`, `READY_FOR_HUMAN_REVIEW`,
  `TRUST_READY_REVIEW`, `APPROVED_FOR_MIGRATION`;
- activation/authority: `V2_AUTHORITY`, `V2_ELIGIBLE_CANARY`, `V2_CANARY`;
- fallback/recovery con nombres y orden distintos.

`final_control_plane_readiness` debe aceptar strings que enumeran manualmente
variantes de otros paquetes, por lo que un cambio local puede romper el agregado
sin error de importación.

**Recomendación:** centralizar enums versionados y usar adapters explícitos en
los bordes.

### MEDIUM — Infraestructura repetida

Todos los paquetes repiten parte de:

- parsing de feature flags;
- `RLock` y contadores;
- snapshots de métricas;
- bounded audit/timeline;
- reportes `human_readable`;
- exports lazy;
- validación de códigos y hashes.

La duplicación aumenta el riesgo de diferencias de seguridad. Por ejemplo, unos
audits validan evento y resultado, otros solo ciertos campos.

**Recomendación:** compartir primitivas pequeñas y sin autoridad:
`FeatureFlag`, `AggregateCounterSet`, `SanitizedCode`, `HashValue`,
`BoundedAuditBuffer` y `ReportEnvelope`.

### MEDIUM — Persistencia insuficiente para evaluación prolongada

Permanecen solo en memoria:

- métricas de todos los módulos;
- timelines y auditorías no SQLite;
- history/trends;
- decisiones de gateway/router;
- health previo;
- detección de cambios de confidence;
- resultados y reportes.

Deberían persistirse de forma agregada:

- ventanas cerradas de métricas;
- cambios de estado y confidence;
- decisiones de routing y fallback;
- hashes de reportes/readiness;
- continuidad y checkpoints de observación.

No deberían persistirse prompts, comandos, parámetros o payloads originales.

### MEDIUM — Concurrencia y recuperación SQLite limitadas

Los stores no configuran WAL, busy timeout, ownership de writer, locking
interproceso ni pruebas de writers concurrentes. La migración de schema es
mínima. `simulate_unexpected_close` aparece como método público de producción.

**Recomendación:** definir un único writer, transacciones `BEGIN IMMEDIATE`,
timeouts, WAL cuando sea apropiado, migrations con rollback y test seams fuera
de la API pública.

### LOW — Nombres y versiones inconsistentes

Conviven sufijos `V1`, `V2` y modelos sin versión. Algunos resultados incluyen
`schema_version`; otros no. `status`, `state`, `health`, `classification` y
`recommendation` se usan de forma intercambiable.

**Recomendación:** aplicar convención:
`<Domain><Kind>V<n>`, `schema_version`, `issued_at`, `source_component` y
`correlation_id/hash`.

### LOW — Reports mezclan idiomas y semántica

Los reportes combinan nombres ingleses, códigos internos y texto español.
Algunos muestran “Approved” aunque el significado sea únicamente revisión.

**Recomendación:** separar contratos/códigos internos del presenter localizado y
usar mensajes que nunca impliquen activación.

## Seguridad

### Verificaciones satisfactorias

- No se detectaron imports hacia Executor, ToolGateway u Orchestrator.
- No se detectaron imports hacia Planner, PolicyEngine o DecisionEngine Legacy.
- No se detectaron imports de `subprocess` ni llamadas a `os.system`/`Popen`.
- No existe conexión desde estos paquetes hacia el runtime productivo.
- Las llamadas `execute` encontradas corresponden a SQLite en los dos módulos
  persistentes, no a ejecución de herramientas.
- No se detectaron ciclos estáticos entre los 14 paquetes.

### Limitaciones

- La ausencia de imports no sustituye una política de dependencias ejecutada en
  CI sobre todo el paquete `sentinel`.
- La invariante `authority=False` / `execution_requested=False` no está
  representada uniformemente.
- Los booleans de readiness/identity/safety no están ligados a evidencia firmada.
- Los routers aislados contienen vocabulario de autoridad V2 que sería peligroso
  conectar sin el safety layer persistente.

## Persistencia

### Persistido actualmente

`authority_safety_layer`:

- estado de operación;
- correlación;
- decisión de autoridad;
- fallback;
- evidence hash;
- timestamps;
- auditoría mínima.

`v2_operational_evidence_storage`:

- hashes de evento/correlación;
- tipo y resultado sanitizados;
- health/incident;
- timestamp e integrity hash.

### Solo en memoria

- métricas y health de todos los demás módulos;
- auditorías y timelines de canary/migration/activation;
- routing cache y replay sets;
- ventanas/trends de long-term evaluation;
- trust history y cambios de confidence;
- resultados finales y reports.

### Estrategia recomendada

Crear un almacenamiento común por envelopes, no una base monolítica:

- tabla append-only de evidence signals firmadas;
- tabla transaccional de operation/idempotency state;
- snapshots agregados de métricas por ventana;
- checkpoints de recovery;
- report hashes y decisiones finales;
- política de retención diferenciada para evidencia crítica.

## Contratos centrales propuestos

### `EvidenceSignalV1`

- `signal_id`
- `schema_version`
- `source_component`
- `source_version`
- `window_id`
- `correlation_hash`
- `signal_type`
- `sanitized_metrics`
- `observed_at`
- `expires_at`
- `payload_hash`
- `previous_signal_hash`
- `integrity_proof`

Reglas: inmutable, sin PII/payload original, timezone-aware, origen permitido,
cadena verificable y expiración obligatoria.

### `ReadinessDecisionV1`

- `decision_id`
- `schema_version`
- `subject`
- `status`
- `confidence`
- `passed_gate_ids`
- `failed_gate_ids`
- `evidence_signal_ids`
- `evidence_set_hash`
- `issued_at`
- `authority: Literal[False]`
- `execution_requested: Literal[False]`

No debe contener estados equivalentes a ACTIVE/AUTHORIZED/EXECUTING.

### `TrustScoreV1`

- `score_id`
- `schema_version`
- `score`
- `confidence_state`
- `criteria_version`
- `positive_factor_codes`
- `negative_factor_codes`
- `window_ids`
- `evidence_set_hash`
- `calculated_at`
- `authority: Literal[False]`
- `execution_requested: Literal[False]`

### `HealthStatusV1`

- `health_id`
- `schema_version`
- `component`
- `state`
- `reason_codes`
- `window_id`
- `observed_at`
- `expires_at`
- `evidence_signal_ids`

Usar un único orden de severidad y mapping explícito desde estados legacy de los
paquetes.

### `AuditEventV1`

- `audit_id`
- `schema_version`
- `event_type`
- `source_component`
- `correlation_hash`
- `result_code`
- `state_before`
- `state_after`
- `occurred_at`
- `evidence_hash`
- `previous_event_hash`
- `integrity_proof`

Debe ser append-only y rechazar contenido no sanitizado.

## Testing

### Cobertura actual

Las 61 suites relacionadas cubren bien:

- flags apagadas por defecto;
- modelos frozen y campos rechazados;
- estados nominales;
- routing determinista;
- fallback lógico;
- idempotencia local;
- corrupción/tampering básico;
- retention;
- clasificación de health/readiness/trust;
- barreras AST por módulo;
- `authority=False` en varios resultados.

### Pruebas repetidas

Se repiten en casi cada paquete:

- scanning AST con implementaciones ligeramente diferentes;
- validación de fields sensibles;
- flag disabled;
- `authority=False`;
- contadores agregados;
- encabezado de reportes.

Estas pruebas deberían mantenerse como invariantes globales parametrizadas,
además de tests unitarios locales.

### Pruebas faltantes

Prioridad alta:

- contrato global de autoridad sobre todas las clases Decision/Result;
- compatibility tests entre outputs e inputs de módulos consecutivos;
- restart E2E: routing → pending → crash → recovery → fallback;
- concurrencia SQLite y doble writer;
- rollback atómico entre safety state y evidence storage;
- signals mezcladas de ventanas/correlaciones distintas;
- evidencia expirada, replay y reordenamiento;
- tampering con hash recalculado;
- property-based tests para tasas, estados y transiciones;
- fuzzing de parsers/códigos;
- tests de migrations forward/backward;
- retención cuando todos los eventos son críticos;
- carga prolongada y límites de memoria;
- full-package dependency policy en CI.

Prioridad media:

- localización de reports;
- monotonicidad de scoring/trust;
- compatibilidad entre versiones de contratos;
- clock skew y timestamps futuros;
- métricas ante overflow o valores extremos.

## Recomendaciones priorizadas

### P0 — Antes de cualquier integración

1. Crear los cinco contratos centrales versionados.
2. Normalizar la invariante no autoritativa en todas las decisiones.
3. Conectar routing/idempotency/fallback a una transacción persistente común.
4. Firmar evidence signals y validar procedencia/ventana/correlación.
5. Sustituir strings/booleans intermodulares por adapters tipados.
6. Convertir las barreras de seguridad en una suite global de CI.

### P1 — Consolidación estructural

1. Unificar feature flags, códigos sanitizados, hashes, auditoría y métricas.
2. Normalizar health, recovery, readiness y activation vocabularies.
3. Definir ownership y orden oficial de Gateway → Policy → Router → Safety.
4. Consolidar migrations y recovery de SQLite.
5. Persistir ventanas, checkpoints y report hashes agregados.

### P2 — Madurez operativa

1. Añadir concurrency, crash, load, fuzz y property tests.
2. Separar presenters localizados de contratos internos.
3. Documentar compatibilidad y deprecación de contratos.
4. Eliminar test seams públicos y APIs no necesarias.

## Próximos pasos

1. No conectar todavía V2 al runtime.
2. Aprobar el modelo de contratos centrales.
3. Implementar primero invariantes globales y adapters, sin migrar lógica.
4. Crear una prueba E2E puramente simulada con persistencia y recovery común.
5. Repetir esta auditoría y exigir cero hallazgos HIGH antes de discutir un
   canary productivo.

## Validación ejecutada

- `pytest`: **31 failed, 2468 passed, 1 skipped, 8 errors** en 579,32 s.
  Los fallos abarcan tests productivos y de arquitectura ya existentes; esta
  auditoría no los corrigió por restricción de alcance.
- `ruff check .`: **19 errores** existentes. Entre ellos hay nombres no
  definidos, imports mal formados, variables sin uso y `except` silenciosos.
- `git diff --check` del único archivo creado: **limpio**.
- Aplicaciones y herramientas ejecutadas por V2: **0**.
- Commits realizados: **0**.

## Conclusión

No existe evidencia de que los módulos auditados ejecuten herramientas o
reemplacen Legacy. La arquitectura demuestra buenas barreras locales, pero aún
es una colección de capas independientes, no un control plane consolidado.

**Legacy Runtime sigue siendo la única autoridad.**

**V2 no ejecuta herramientas.**

**No existe cutover.**

**No existe activación automática.**
