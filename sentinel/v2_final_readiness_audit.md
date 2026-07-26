# SENTINEL V2 FINAL ARCHITECTURAL READINESS AUDIT

## Resultado

**Clasificación: BLOCKED**

**Puntuación de preparación arquitectónica: 72/100**

La puntuación indica madurez suficiente para continuar revisión y
consolidación, no autorización para activar V2. No se encontró una ruta V2 que
ejecute herramientas o procesos, pero persisten incumplimientos contractuales
y de dependencias que bloquean cualquier activación futura.

Estados que este reporte nunca concede: `ACTIVE`, `AUTHORIZED`, `EXECUTING` y
`CUTOVER_READY`.

## 1. Autoridad

- No se encontró `authority=True` ni `execution_requested=True` en módulos V2.
- `action_requested` y `authority_explicit` solo aparecen como cadenas de
  rechazo en `contract_adapters/authority_adapter.py`; no son campos de
  consumidores.
- Los resultados consolidados heredan `DecisionResultV1`.
- `ReplayExecutionResultV1` y `RuntimeShadowResultV1` siguen heredando
  `BaseModel`, declaran `authority=False`, pero carecen del campo central
  `execution_requested=False`.
- `PolicyDecisionV2` es un contrato de política futuro y todavía no hereda el
  resultado central no autoritativo.

Conclusión: no existe autoridad ejecutable confirmada, pero la invariante no
está aplicada globalmente.

## 2. Dependencias y ejecución

El análisis AST no encontró imports hacia Executor, ToolGateway u Orchestrator,
ni llamadas a `os.system` o process spawning en las capas de control V2.
Sí encontró una dependencia directa de `subprocess` en
`local_model/runtime.py`; aunque pertenece al runtime de modelo local y no a
una capa de autoridad V2, incumple el criterio global solicitado.

Bloqueadores:

- `adapters/plan_adapter.py` importa `sentinel.core.planner`.
- `shadow/observer.py` importa `sentinel.core.planner.Plan`.
- `shadow/runtime_adapter.py` importa `sentinel.core.planner.Plan`.
- `local_model/runtime.py` importa `subprocess`.

Los imports de Planner son dependencias Legacy y contradicen el límite
arquitectónico solicitado. El import de `subprocess` amplía la superficie de
ejecución del perímetro global, aunque la auditoría no encontró que las capas
de decisión V2 lo invoquen. La mención `popen` en
`promotion_validation/gates.py` pertenece a una lista de patrones prohibidos,
no a una llamada.

## 3. Contratos

Contratos centrales verificados:

- `DecisionResultV1`
- `EvidenceSignalV1`
- `HealthStatusV1`
- `AuditEventV1`
- `ReadinessResultV1`

Fortalezas:

- modelos inmutables y `extra="forbid"`;
- autoridad y solicitud de ejecución limitadas a `False`;
- health, readiness y audit consolidados;
- evidencia firmada no contiene payloads.

Gaps:

- dos resultados diagnósticos aún no usan `DecisionResultV1`;
- `PolicyDecisionV2` conserva una jerarquía contractual anterior;
- quedan aliases públicos temporales de vocabularios consolidados.

## 4. Persistencia

Verificado:

- `persistent_control_boundary`: WAL, foreign keys, `BEGIN IMMEDIATE`,
  idempotencia persistente, transición validada, rollback lógico e integrity
  check;
- `operational_telemetry_hub`: WAL, foreign keys, transacciones, timeline
  referencial, hashes canónicos y snapshots agregados;
- Evidence Storage: restricción única contra replay de evidencia firmada.

Riesgos:

- existen tres stores SQLite aislados y no hay migración/retención común;
- snapshots de telemetry no tienen todavía API pública de revalidación;
- métricas en memoria no se reconstruyen automáticamente tras reinicio;
- SQLite sigue limitado a coordinación local de un host.

## 5. Seguridad criptográfica

Verificado mediante pruebas:

- firma Ed25519 válida;
- issuer conocido mediante registro de claves públicas;
- hash canónico del payload;
- rechazo de metadata o payload manipulado;
- expiración;
- replay en memoria y restricción persistente;
- claves privadas no forman parte de contratos ni storage.

Bloqueadores operativos futuros:

- falta rotación y revocación de identidades;
- falta una política de custodia de claves privadas;
- la revalidación histórica ante revocación no está implementada.

## 6. Métricas, observabilidad y reportes

- `operational_telemetry_hub` es la única frontera SQLite para métricas
  operacionales consolidadas.
- Los snapshots locales restantes son contadores mínimos en memoria.
- No se encontraron stores SQLite de métricas paralelos.
- Los reportes auditados son presentadores: no definen métodos `decide`,
  `evaluate`, `activate`, `route`, `execute` o `launch`.
- El hub acepta eventos `UNKNOWN`; una integración futura deberá exigir
  `VERIFIED` cuando el evento provenga de evidencia criptográfica.

## 7. Feature flags

Todos permanecen desactivados por defecto.

| Flag | Módulo | Propósito | Estado actual | Riesgo |
|---|---|---|---|---|
| `OPERATIONAL_TELEMETRY_HUB_ENABLED` | telemetry hub | Métricas persistentes | `False` | Bajo |
| `PERSISTENT_CONTROL_BOUNDARY_ENABLED` | control boundary | Idempotencia/rollback | `False` | Medio |
| `V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED` | evidence storage | Evidencia local | `False` | Medio |
| `V2_OPERATIONAL_OBSERVABILITY_ENABLED` | observability | Observación agregada | `False` | Bajo |
| `FINAL_CONTROL_PLANE_READINESS_ENABLED` | final readiness | Revisión humana | `False` | Bajo |
| `V2_TRUST_EVALUATION_ENABLED` | trust evaluation | Score agregado | `False` | Bajo |
| `CONTROLLED_RUNTIME_ACTIVATION_ENABLED` | controlled activation | Canary lógico | `False` | Alto si se activa |
| `V2_CANARY_ENABLED` | controlled activation | Routing canary | `False` | Alto si se activa |
| `V2_AUTHORITY_MIGRATION_ENABLED` | authority migration | Autoridad limitada simulada | `False` | Alto si se activa |
| `ACTIVATION_GATEWAY_ENABLED` | activation gateway | Elegibilidad | `False` | Medio |
| `AUTHORIZATION_CANARY_ENABLED` | authorization canary | Grants simulados | desactivado | Medio |
| `CANARY_ENVIRONMENT_ENABLED` | canary environment | Entorno aislado | `False` | Bajo |
| `CANARY_OBSERVATION_ENABLED` | canary observation | Observación pasiva | `False` | Bajo |
| `RUNTIME_CANARY_ENABLED` | runtime canary | Pipeline paralelo | `False` | Medio |
| `RUNTIME_V2_ROUTING_ENABLED` | controlled runtime | Routing shadow | `False` | Medio |
| `V2_COMPARISON_ENABLED` | controlled runtime | Comparación | `False` | Bajo |
| `RUNTIME_TRIAL_ENABLED` | runtime trial | Simulación | `False` | Bajo |
| `RUNTIME_REPLAY_VALIDATION_ENABLED` | replay | Replay sanitizado | `False` | Bajo |
| `RUNTIME_EQUIVALENCE_VALIDATION_ENABLED` | equivalence | Equivalencia | `False` | Bajo |
| `DECISION_SHADOW_VALIDATION_ENABLED` | decision shadow | Comparación | `False` | Bajo |
| `DECISION_LONG_TERM_ENABLED` | long-term evaluation | Tendencias | `False` | Bajo |
| `V2_AUTHORITY_READINESS_ENABLED` | authority readiness | Gates | `False` | Bajo |
| `PROMOTION_VALIDATION_ENABLED` | promotion validation | Gates de promoción | `False` | Bajo |
| `CUTOVER_VALIDATION_ENABLED` | cutover validation | Evidencia de readiness | `False` | Bajo |
| `STABILITY_VALIDATION_ENABLED` | stability | Estabilidad | `False` | Bajo |

## Riesgos por severidad

### Críticos

No se confirmó una vulnerabilidad crítica ni una ruta de ejecución V2.

### Altos

- imports directos de Planner Legacy desde adapters/Shadow;
- dependencia de `subprocess` en el runtime de modelo local;
- invariante contractual incompleta en dos resultados diagnósticos;
- ausencia de rotación/revocación antes de confiar en evidencia a largo plazo.

### Medios

- stores SQLite separados sin lifecycle común;
- replay en memoria limitado al proceso, complementado por uniqueness local;
- telemetry permite eventos de integridad `UNKNOWN`;
- métricas no reconstruidas desde snapshots.

### Bajos

- aliases públicos temporales;
- snapshots locales con formas diferentes;
- fallo preexistente de tests que resuelve rutas relativas desde un cwd
  incorrecto.

## Bloqueadores para cualquier activación futura

1. Eliminar imports de Planner Legacy desde adapters y `sentinel/shadow`.
2. Separar `local_model/runtime.py` del perímetro V2 o encapsular y auditar su
   dependencia de `subprocess`.
3. Migrar todos los resultados diagnósticos a `DecisionResultV1`.
4. Definir rotación, revocación y custodia de claves.
5. Exigir evidencia `VERIFIED` en fronteras que influyan readiness.
6. Diseñar migración, retention y recovery coordinado de stores.
7. Obtener una suite V2/global verde desde un entorno de test reproducible.

## Confirmaciones

**Legacy Runtime continúa siendo la única autoridad.**

**V2 no ejecuta herramientas.**

**No existe cutover.**

**No existe activación automática.**
