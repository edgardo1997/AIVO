# ADR-001: Runtime Consolidation

**Architecture Decision Record**

---

## Contexto

Sentinel tiene dos sistemas de orquestación paralelos:

1. **`Orchestrator`** (2035 líneas, `orchestrator.py`) — Activo en producción.
   Maneja: intent parsing (v1), planning, simulación, risk classification,
   decision engine, execution, audit, memory, multi-agent, offline queue.
   30+ dependencias inyectadas en el constructor.

2. **`IntelligenceOrchestrator`** (349 líneas, `intelligence_orchestrator.py`)
   — Nunca instanciado en runtime. Maneja: capability-based model selection,
   performance scoring, model ranking, time prediction.

Además, 12 componentes de Phase 9-10 (CapabilityEngine, IntentEngineV2,
ConversationManager, ModelCoordinator, FusionEngine, ResourceIntelligenceLayer,
PerformanceIntelligence, FeedbackEngine, ModelRanking, TimePredictor,
ModelDiscovery, EventBus suscriptores) existen pero no están conectados al runtime.

## Problema

- No existe un punto único de entrada para las operaciones del sistema.
- La lógica de inteligencia (Phase 9-10) no produce valor en producción.
- La seguridad tiene un bypass documentado (ModelRouter → ToolGateway sin policy).
- No hay separación clara entre decisión y ejecución.
- La deuda técnica incluye 21% de código muerto en runtime.

## Decisión

Crear **`SentinelRuntime`** como el punto único de entrada para toda operación.

### Estrategia de migración

```
FASE 0 (actual):                      Dos sistemas paralelos
  Orchestrator (producción)
  IntelligenceOrchestrator (tests)

FASE 1 (inmediata):                   Contrato + clasificación
  Crear SentinelRuntime como clase contenedora
  Documentar componentes como KEEP/MERGE/REFACTOR/REMOVE/DEFER
  NO cambiar el runtime existente

FASE 2 (corto plazo):                 Conectar inteligencia
  Fusionar Orchestrator → SentinelRuntime
  Fusionar IntelligenceOrchestrator → SentinelRuntime.learning_layer
  Conectar PerformanceIntelligence a ToolGateway
  Conectar FeedbackEngine a endpoint de feedback
  Conectar ModelRanking a ModelRouter._smart_select()
  Conectar IntentEngineV2 como reemplazo de v1

FASE 3 (medio plazo):                 Seguridad
  Forzar PolicyEngine en ModelRouter._handle_tool_calls()
  Eliminar bypass de tool calling
  Unificar tipos (IntentCategory como único)

FASE 4 (largo plazo):                 Eliminar deuda
  REFACTOR Orchestrator legacy (dividir en sub-capas)
  REFACTOR ModelRouter (separar ProviderSelector, CircuitBreaker, ToolExecutor)
  MERGE o REMOVE componentes DEFER (FusionEngine)
```

### Mapa de componentes post-migración

```
SentinelRuntime
  │
  ├── IntentLayer
  │     └── IntentEngineV2 (hereda de v1)
  │
  ├── PlanningLayer
  │     └── Planner (existente, sin cambios)
  │
  ├── PolicyLayer
  │     ├── PolicyEngine (existente)
  │     ├── DecisionEngine (existente)
  │     ├── RiskClassifier (existente)
  │     └── ConsentService (existente)
  │
  ├── ExecutionLayer
  │     ├── ToolGateway (gate ÚNICO, con policy obligatorio)
  │     ├── ProviderSelector (extraído de ModelRouter)
  │     ├── CircuitBreaker (extraído de ModelRouter)
  │     └── FallbackManager (extraído de ModelRouter)
  │
  ├── LearningLayer
  │     ├── PerformanceIntelligence (métricas)
  │     ├── FeedbackEngine (feedback usuario)
  │     ├── ModelRanking (ranking dinámico)
  │     ├── TimePredictor (predicción)
  │     └── ModelDiscovery (auto-descubrimiento)
  │
  └── InfrastructureLayer
        ├── ContextEngine (existente)
        ├── AuditService (existente)
        ├── Memory (existente)
        ├── EventBus (con suscriptores reales)
        └── RateLimiter (existente)
```

## Consecuencias

### Positivas
- Un único punto de entrada verificable.
- Todos los módulos inteligentes producen valor real.
- Los bypasses de seguridad se eliminan por diseño.
- La auditoría cubre todas las operaciones.
- Las decisiones son explicables (incluyen métricas + ranking).

### Negativas
- Migración requiere cambios en `modules/__init__.py` y `sidecar/main.py`.
- `Orchestrator` tiene 2035 líneas de lógica probada — la migración debe ser
  incremental para no romper la pipeline existente.
- Algunos componentes (FusionEngine) requieren rediseño completo.

### Neutrales
- La API pública (`/api/sentinel/chat`, `/api/sentinel/process`) no cambia.
- Los routers existentes siguen funcionando (llaman a `SentinelRuntime.process()`).
- El ToolGateway sigue siendo el gate de ejecución, ahora con policy obligatorio.

## Estado

**Aprobado.** Pendiente de implementación.

## Referencias

- `docs/architecture/runtime_graph.md` — Mapa de dependencias actual
- `docs/architecture/runtime_trace.md` — Traza de ejecución real
- `docs/architecture/component_registry.md` — Clasificación de componentes
- `docs/architecture/runtime_rules.md` — Reglas de gobierno
- `sentinel/core/runtime.py` — Implementación del contrato
- `docs/production_certification/architecture_audit.md` — Hallazgos de auditoría

## Firmantes

- Arquitecto Principal de Software
- Staff Software Engineer
- Ingeniero Senior de Sistemas Distribuidos
- SRE
- QA Lead

---

## Apéndice: Timeline Estimado

| Fase | Duración | Dependencias |
|---|---|---|
| FASE 1: Contrato + documentación | 1 semana | Ninguna |
| FASE 2: Conectar inteligencia | 2-3 semanas | FASE 1 |
| FASE 3: Seguridad | 1-2 semanas | FASE 1 |
| FASE 4: Eliminar deuda | 4-6 semanas | FASE 2 + 3 |
| **Total** | **8-12 semanas** | |
