# Component Registry — Clasificación y Decisión

> Catálogo oficial de todos los componentes del sistema Sentinel.
> Cada componente recibe una acción: KEEP | MERGE | REFACTOR | REMOVE | DEFER

---

## Clasificación

| Acción | Significado |
|---|---|
| **KEEP** | Mantener como está. Funciona correctamente. |
| **MERGE** | Fusionar con otro componente. Existe duplicación. |
| **REFACTOR** | Reestructurar internamente. La responsabilidad es correcta pero la implementación no. |
| **REMOVE** | Eliminar. Código muerto, obsoleto o reemplazado. |
| **DEFER** | Posponer. No es prioritario, no afecta al runtime actual. |

---

## Tabla de Decisión

| Componente | Archivo | Líneas | Runtime | Acción | Justificación |
|---|---|---|---|---|---|
| `Orchestrator` | `orchestrator.py` | 2035 | Activo | **REFACTOR** | God class. 30 dependencias. Debe dividirse en sub-módulos (Intent, Planning, Policy, Execution, Learning) sin perder la pipeline existente. |
| `IntelligenceOrchestrator` | `intelligence_orchestrator.py` | 349 | Inactivo | **MERGE** → Orchestrator | Representa la arquitectura futura. Debe absorber gradualmente CapabilityEngine, ModelRanking, PerformanceIntelligence, FeedbackEngine. |
| `ModelRouter` | `model_router.py` | 1664 | Activo | **REFACTOR** | God class. Separar en: ProviderSelector, CircuitBreaker, ToolExecutor, FallbackManager. Mantener la API pública igual. |
| `ToolGateway` | `tool_gateway.py` | 480 | Activo | **KEEP** | Punto de seguridad único. Bien diseñado. Añadir rate limiting por tool. |
| `PolicyEngine` | `policy_engine.py` | 214 | Activo | **KEEP** | Correcto. Asegurar que ModelRouter tool calling también pase por aquí. |
| `DecisionEngine` | `decision_engine.py` | 334 | Activo | **KEEP** | Correcto. Risk assessment objetivo funciona. |
| `IntentEngine v1` | `intent.py` | 584 | Activo | **MERGE** → IntentEngineV2 | v2 es superior (multi-capa, más categorías). Migrar. |
| `IntentEngineV2` | `intent_engine_v2.py` | 645 | Inactivo | **MERGE** ← IntentEngine v1 | Reemplazar v1. Ya tiene `to_intent()` para compatibilidad. |
| `CapabilityEngine` | `capability_engine.py` | 162 | Inactivo | **MERGE** → IntelligenceOrchestrator | Debe ser parte del nuevo pipeline de decisión. |
| `ConversationManager` | `conversation_manager.py` | 471 | Inactivo | **KEEP** | No eliminar. Bien diseñado. Falta: conexión con chat_tools.py y persistencia. |
| `ModelCoordinator` | `model_coordinator.py` | 423 | Inactivo | **MERGE** → Orchestrator | La lógica de multi-step debe integrarse en Orchestrator. |
| `FusionEngine` | `fusion_engine.py` | 242 | Inactivo | **DEFER** | No puede fusionar realmente (solo concatena). Requiere rediseño completo. No blocker. |
| `ResourceIntelligenceLayer` | `resource_intelligence.py` | 340 | Inactivo | **KEEP** | Arquitectura correcta. Falta: conexión con ModelRouter.select(). |
| `PerformanceIntelligence` | `performance_intelligence.py` | 206 | Inactivo | **KEEP** | Bien diseñado. Falta: integrar con Orchestrator._execute_single_step(). |
| `FeedbackEngine` | `feedback_engine.py` | 172 | Inactivo | **KEEP** | Bien diseñado. Falta: conectar con API endpoint de feedback. |
| `ModelRanking` | `model_ranking.py` | 263 | Inactivo | **KEEP** | Bien diseñado. Falta: conectar con ModelRouter._smart_select(). |
| `TimePredictor` | `time_predictor.py` | 161 | Inactivo | **KEEP** | Bien diseñado. Falta: conectar con respuesta al usuario. |
| `ModelDiscovery` | `model_discovery.py` | 476 | Inactivo | **KEEP** | Bien diseñado. Falta: periodic refresh y conexión con ModelRegistry. |
| `ContextEngine` | `context.py` | 259 | Activo | **KEEP** | Correcto. Cache de 2s, recolección paralela. |
| `AuditService` | `services/audit_service.py` | 139 | Activo | **KEEP** | Correcto. Sanitiza, redacta, verifica integridad. |
| `ConsentService` | vía modules | — | Activo | **KEEP** | Correcto. Integrado con DecisionEngine. |
| `Planner` | `planner.py` | — | Activo | **KEEP** | Correcto. |
| `RiskClassifier` | — | — | Activo | **KEEP** | Correcto. |
| `SimulationEngine` | — | — | Activo | **KEEP** | Correcto. |
| `ModelFeedbackStore` | `model_feedback.py` | — | Activo | **KEEP** | Usado por ModelRouter._smart_select(). |
| `CostTracker` | `cost_tracker.py` | — | Activo | **KEEP** | Usado por model_router. |
| `PerformanceTracker` | `performance_tracker.py` | — | Activo | **KEEP** | Usado por Orchestrator._execute_single_step(). |
| `EventBus` | `event_bus.py` | 66 | Inactivo | **KEEP** | Infraestructura lista. Falta: suscriptores. |

---

## Árbol de Decisión

```
¿Está activo en runtime?
  ├── SÍ → ¿Está bien diseñado?
  │        ├── SÍ → KEEP (ToolGateway, PolicyEngine, ContextEngine, AuditService, etc.)
  │        └── NO → REFACTOR (Orchestrator, ModelRouter)
  │
  └── NO → ¿Es necesario?
           ├── SÍ → ¿Duplica funcionalidad existente?
           │      ├── SÍ → MERGE (IntentEngineV2 ← v1, IntelligenceOrchestrator → Orchestrator)
           │      └── NO → KEEP (PerformanceIntelligence, FeedbackEngine, etc.)
           │                + Falta: conexión con runtime
           │
           └── NO → ¿Puede ser útil en el futuro?
                    ├── SÍ → DEFER (FusionEngine)
                    └── NO → REMOVE (nada en esta categoría)
```

---

## Arquitectura Objetivo (Post-Migración)

```
SentinelRuntime (antes Orchestrator + IntelligenceOrchestrator)
  │
  ├── IntentLayer (antes IntentEngine v1 + v2 fusionados)
  │     └── IntentEngineV2 con parser multi-capa
  │
  ├── PlanningLayer (Planner existente)
  │
  ├── PolicyLayer (PolicyEngine + DecisionEngine + RiskClassifier existentes)
  │     └── GATE ÚNICO para toda ejecución de herramientas
  │
  ├── ExecutionLayer (ToolGateway + ModelRouter fragmentado)
  │     ├── ProviderSelector
  │     ├── CircuitBreaker
  │     ├── ToolExecutor (con policy gate obligatorio)
  │     └── FallbackManager
  │
  └── LearningLayer (nuevo, desde Phase 9-10)
        ├── PerformanceIntelligence (métricas)
        ├── FeedbackEngine (feedback usuario)
        ├── ModelRanking (ranking dinámico)
        ├── TimePredictor (predicción)
        └── ModelDiscovery (auto-descubrimiento)
```

---

## Dependencias entre Componentes (Post-Migración)

```
SentinelRuntime
  ├── IntentLayer ──→ IntentEngineV2
  ├── PlanningLayer ──→ Planner
  ├── PolicyLayer ──→ PolicyEngine
  │                  └── DecisionEngine
  │                  └── RiskClassifier
  │                  └── ConsentService
  │
  ├── ExecutionLayer ──→ ToolGateway (gate único)
  │                     └── ProviderSelector
  │                     └── CircuitBreaker
  │                     └── FallbackManager
  │
  └── LearningLayer ──→ PerformanceIntelligence ← ExecutionLayer
                       └── FeedbackEngine ← API endpoint
                       └── ModelRanking ← PerformanceIntelligence + FeedbackEngine
                       └── TimePredictor ← PerformanceIntelligence
                       └── ModelDiscovery → ModelRegistry
```

Todas las arrows son en una dirección: LearningLayer consume datos, no produce decisiones
directamente. Las decisiones las toma PolicyLayer + ExecutionLayer basándose en
recomendaciones de LearningLayer.
