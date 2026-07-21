# ARCHITECTURE_REVIEW.md

## FASE 1: AUDITORÍA ARQUITECTÓNICA

**Fecha**: 2025-01-17
**Versión**: Sentinel v2.0 (evolución en progreso)
**Propósito**: Análisis completo de la arquitectura existente antes de implementar mejoras

---

## 1. COMPONENTES EXISTENTES

### 1.1 Capa de Orquestación Principal

#### Orchestrator (`sentinel/core/orchestrator.py`)
**Responsabilidad**: Coordinador central del flujo de ejecución
**Dependencias**: 
- IntentEngine, ToolGateway, Planner, DecisionEngine
- ModelRouter, ContextEngine, MemoryBackend
- SimulationEngine, AdvisoryService, KnowledgeBase
- Múltiples servicios auxiliares (cost, performance, recovery, etc.)

**Estado**: ✅ **SÓLIDO** - Bien estructurado con separación de responsabilidades
**Riesgos**: 
- Demasiadas dependencias directas (22 componentes inyectados)
- Posible acoplamiento alto con componentes específicos
- Difícil de testear en aislamiento

**Integración Clave**: Punto central donde convergen todos los componentes

#### IntentEngine (`sentinel/core/intent.py`)
**Responsabilidad**: Detección y clasificación de intenciones del usuario
**Dependencias**: ModelRouter (opcional)
**Estado**: ⚠️ **NECESITA MEJORAS** - Usa patrones regex pero sin grounding
**Riesgos**:
- No valida información verificable contra herramientas
- No integra con sistema de aprendizaje del entorno
- La confianza del intent es default 1.0 sin ajuste dinámico

**Integración Clave**: Primer punto del pipeline donde se requiere grounding

#### Planner (`sentinel/core/planner.py`)
**Responsabilidad**: Generación de planes de ejecución
**Dependencias**: Intent, CapabilityRegistry, GoalRegistry, ModelRouter
**Estado**: ✅ **SÓLIDO** - Bien estructurado con sistema de pasos
**Riesgos**:
- No integra con Application Discovery Service
- No usa conocimiento del entorno para planes inteligentes
- Fallback a `system.info` para cualquier target desconocido

**Integración Clave**: Donde se debe integrar conocimiento de aplicaciones

#### DecisionEngine (`sentinel/core/decision_engine.py`)
**Responsabilidad**: Evaluación de riesgos y toma de decisiones
**Dependencias**: ModelRouter (opcional, para LLM advisor)
**Estado**: ❌ **CRÍTICO** - Usa LLM con autoridad en decisiones de riesgo
**Riesgos**:
- LLM tiene influencia directa en risk scores (líneas 156-169)
- No hay validación estricta de salida del LLM
- No hay fallback cuando el LLM falla
- No hay registro de incertidumbre

**Integración Clave**: Punto crítico donde el modelo NO debe tener autoridad

### 1.2 Capa de Seguridad y Confianza

#### ToolGateway (`sentinel/core/tool_gateway.py`)
**Responsabilidad**: Único punto de acceso a herramientas
**Dependencias**: PolicyEngine, ContextEngine, QualityGate
**Estado**: ✅ **EXCELENTE** - Implementa correctamente el flujo de seguridad
**Riesgos**:
- No implementa validación de grounding
- No integra con Grounding Engine

**Integración Clave**: Componente correcto que requiere extensión para grounding

#### PolicyEngine (`sentinel/core/policy_engine.py`)
**Responsabilidad**: Aplicación de políticas de seguridad
**Dependencias**: PolicyStore (carga políticas desde YAML)
**Estado**: ✅ **SÓLIDO** - Bien diseñado con sistema de permisos
**Riesgos**: 
- No integra con Grounding Engine para validar datos

**Integración Clave**: Autoridad final en decisiones de seguridad

#### QualityGate (`sentinel/core/quality_gate.py`)
**Responsabilidad**: Filtrado de información sensible en resultados
**Dependencias**: Output policies (patrones de datos sensibles)
**Estado**: ✅ **SÓLIDO** - Implementa redacción de datos sensibles
**Riesgos**:
- No valida información antes de que llegue al modelo

**Integración Clave**: Componento correcto para proteger datos sensibles

#### AdvisoryService (`sentinel/advisory/service.py`)
**Responsabilidad**: Capa de confianza y advisory (post-procesamiento)
**Dependencias**: ConfidenceEngine, AdvisoryConfig
**Estado**: ✅ **EXCELENTE** - Diseño correcto como observador sin autoridad
**Riesgos**: Ninguno significativo

**Integración Clave**: Buen patrón a seguir para separación de responsabilidades

#### Confirmation (`sentinel/core/confirmation.py`)
**Responsabilidad**: Gestión de confirmaciones de usuario
**Dependencias**: Sistema de almacenamiento de grants
**Estado**: ✅ **SÓLIDO** - Implementa flujo de confirmación
**Riesgos**:
- No integra con evaluación de riesgo mejorada

**Integración Clave**: Donde debe integrarse Risk Assessment mejorado

#### CircuitBreaker (`sentinel/core/circuit_breaker.py`)
**Responsabilidad**: Protección contra fallos en cascada
**Dependencias**: Ninguna
**Estado**: ✅ **SÓLIDO** - Implementa patrón circuit breaker
**Riesgos**: Ninguno significativo

### 1.3 Capa de Contexto

#### ContextEngine (`sentinel/core/context.py`)
**Responsabilidad**: Recopilación de estado del sistema
**Dependencias**: psutil (librería de sistema)
**Estado**: ✅ **SÓLIDO** - Recopila datos del sistema correctamente
**Riesgos**:
- Datos recopilados no se usan como grounding obligatorio
- No hay validación de frescura de datos
- No hay sanitización de información sensible

**Integración Clave**: Fuente de datos para Grounding Engine

#### DeepContextEngine (`sentinel/core/deep_context.py`)
**Responsabilidad**: Enriquecimiento de contexto con apps, fleet, goals
**Dependencias**: SystemContextEngine, múltiples funciones de callback
**Estado**: ⚠️ **PARCIAL** - Tiene hooks pero no implementa descubrimiento real
**Riesgos**:
- `app_discovery_fn` es un hook no implementado
- No hay Application Discovery Service real
- No hay App Knowledge Engine

**Integración Clave**: Donde debe integrarse Application Discovery Service

#### CapabilityRegistry (`sentinel/core/capability_registry.py`)
**Responsabilidad**: Registro de capacidades disponibles
**Dependencias**: Ninguna
**Estado**: ✅ **SÓLIDO** - Sistema de registro bien diseñado
**Riesgos**:
- No se integra con descubrimiento automático de capacidades

**Integración Clave**: Registro de capacidades debe integrarse con Application Discovery

### 1.4 Capa de Modelos

#### ModelRouter (`sentinel/core/model_router.py`)
**Responsabilidad**: Enrutamiento a diferentes proveedores de IA
**Dependencias**: CircuitBreaker, base de datos (opcional)
**Estado**: ⚠️ **NECESITA MEJORAS** - Selecciona por task_type pero no por hardware
**Riesgos**:
- No analiza capacidad del hardware
- No hay perfil del dispositivo
- No hay optimización según hardware disponible
- Usa siempre el mismo modelo sin considerar capacidad

**Integración Clave**: Donde debe integrarse Model Capability Manager

#### AgentRegistry (`sentinel/core/agent.py`)
**Responsabilidad**: Gestión de agentes especializados
**Dependencias**: ModelRouter (opcional), repositorio (opcional)
**Estado**: ⚠️ **NECESITA MEJORAS** - Sistema de puntuación simple
**Riesgos**:
- No hay validación de que el agente pueda manejar la tarea
- Sistema de puntuación puede seleccionar agentes inapropiados

**Integración Clave**: Debe integrarse con Model Capability Manager

### 1.5 Capa de Recuperación

#### Recovery (RetryHandler, FallbackHandler, RollbackManager)
**Responsabilidad**: Manejo de errores y recuperación
**Dependencias**: ErrorClassifier
**Estado**: ✅ **SÓLIDO** - Sistema de recuperación bien diseñado
**Riesgos**: Ninguno significativo

### 1.6 Capa de Observabilidad

#### ObservabilityService (`sentinel/core/observability.py`)
**Responsabilidad**: Métricas y traces de ejecución
**Dependencias**: Ninguna
**Estado**: ✅ **SÓLIDO** - Sistema de observabilidad bien diseñado
**Riesgos**:
- Expone información interna que debería filtrarse en modo usuario

**Integración Clave**: Debe integrarse con Presentation Layer

#### CostTracker (`sentinel/core/cost_tracker.py`)
**Responsabilidad**: Seguimiento de costos de API
**Dependencias**: Ninguna
**Estado**: ✅ **SÓLIDO** - Sistema de costos bien diseñado

#### PerformanceTracker (`sentinel/core/performance_tracker.py`)
**Responsabilidad**: Métricas de performance
**Dependencias**: Ninguna
**Estado**: ✅ **SÓLIDO** - Sistema de performance bien diseñado

### 1.7 Capa de Memoria

#### MemoryBackend (`sentinel/core/operational_memory.py`)
**Responsabilidad**: Almacenamiento de memoria operacional
**Dependencias**: Repositorio de base de datos
**Estado**: ⚠️ **NECESITA MEJORAS** - No separa tipos de memoria
**Riesgos**:
- No hay metadata de fuente, fecha, confianza
- No hay mecanismo de invalidación
- No hay separación entre tipos de memoria

**Integración Clave**: Debe extenderse para soportar memoria confiable

#### KnowledgeBase (`sentinel/core/knowledge_base.py`)
**Responsabilidad**: Base de conocimiento persistente
**Dependencias**: Repositorio de base de datos
**Estado**: ⚠️ **PARCIAL** - Existe pero no se usa sistemáticamente
**Riesgos**:
- No se integra con sistema de confianza
- No se usa para conocimiento de aplicaciones

**Integración Clave**: Debe integrarse con Reliable Memory y Application Discovery

### 1.8 Capa de Simulación

#### SimulationEngine (`sentinel/core/simulation.py`)
**Responsabilidad**: Simulación de impacto antes de ejecución
**Dependencias**: Ninguna
**Estado**: ✅ **SÓLIDO** - Sistema de simulación bien diseñado
**Riesgos**:
- Predicciones son estimaciones sin validación real
- No hay detección de comandos peligrosos robusta

**Integración Clave**: Fuente de datos objetivos para Decision Engine

### 1.9 Capa de Integración

#### SentinelBridge (`sidecar/modules/sentinel_bridge.py`)
**Responsabilidad**: Puente entre API HTTP y Sentinel
**Dependencias**: Orchestrator, múltiples servicios
**Estado**: ⚠️ **NECESITA MEJORAS** - Mezcla lógica de negocio con API
**Riesgos**:
- Contiene lógica de negocio que debería estar en el dominio
- No usa Presentation Layer para filtrar respuestas
- Expone información interna sin filtrado

**Integración Clave**: Donde debe integrarse Presentation Layer

#### AIService (`sidecar/services/ai_service.py`)
**Responsabilidad**: Servicio de IA para chat
**Dependencias**: ModelRouter, ContextWindowManager, Vault
**Estado**: ⚠️ **NECESITA MEJORAS** - Mezcla configuración con lógica
**Riesgos**:
- Mezcla lógica de presentación con acceso a vault y router
- No integra con Grounding Engine

### 1.10 Capa de Frontend

#### Workbench (`src/components/Workbench/Workbench.tsx`)
**Responsabilidad**: Interfaz principal de usuario
**Dependencias**: API client, estado React
**Estado**: ❌ **CRÍTICO** - Expone detalles internos del sistema
**Riesgos**:
- Muestra etapas internas del pipeline
- Expone risk scores y métricas internas
- No hay separación modo usuario/desarrollador
- Contiene lógica de negocio de seguridad

**Integración Clave**: Donde debe implementarse modo usuario/desarrollador

---

## 2. DEPENDENCIAS Y ACOPLAMIENTO

### 2.1 Grafo de Dependencias Principales

```
Orchestrator (CENTRAL)
├── IntentEngine
│   └── ModelRouter (opcional)
├── ToolGateway
│   ├── PolicyEngine
│   │   └── PolicyStore
│   ├── ContextEngine
│   └── QualityGate
├── Planner
│   ├── CapabilityRegistry
│   ├── GoalRegistry
│   └── ModelRouter
├── DecisionEngine
│   └── ModelRouter (opcional, para LLM)
├── ModelRouter
│   ├── CircuitBreaker
│   ├── CostTracker
│   └── ModelFeedbackStore
├── ContextEngine
├── DeepContextEngine
│   └── SystemContextEngine
├── SimulationEngine
├── AdvisoryService
│   └── ConfidenceEngine
├── MemoryBackend
├── KnowledgeBase
└── [Múltiples servicios auxiliares]
```

### 2.2 Puntos de Alto Acoplamiento

1. **Orchestrator → 22 componentes**: 
   - **Riesgo**: Difícil de testear, mantener y extender
   - **Recomendación**: Considerar patrón Facade o inyección selectiva

2. **DecisionEngine → ModelRouter**:
   - **Riesgo**: Acoplamiento con infraestructura de modelos
   - **Recomendación**: Usar patrón Strategy para diferentes advisors

3. **SentinelBridge → Orchestrator y múltiples servicios**:
   - **Riesgo**: Mezcla de capas (API → dominio)
   - **Recomendación**: Mover lógica de negocio a servicios dedicados

4. **Workbench → API directa sin filtrado**:
   - **Riesgo**: Exposición de detalles internos
   - **Recomendación**: Implementar Presentation Layer

### 2.3 Dependencias Circulares Potenciales

1. **Orchestrator → DecisionEngine → ModelRouter → Orchestrator**:
   - **Estado**: Actualmente resuelto por inyección opcional
   - **Riesgo**: Puede convertirse en circular con nuevas integraciones

2. **IntentEngine → ModelRouter → Orchestrator → IntentEngine**:
   - **Estado**: Actualmente resuelto
   - **Riesgo**: Debe mantenerse al integrar Grounding Engine

---

## 3. RIESGOS ARQUITECTÓNICOS

### 3.1 Riesgos Críticos (requieren atención inmediata)

#### RIESGO 1: DecisionEngine usa LLM con autoridad
**Severidad**: CRÍTICA
**Ubicación**: `sentinel/core/decision_engine.py` líneas 156-169
**Impacto**: El modelo puede influir indebidamente en decisiones de seguridad
**Probabilidad**: ALTA
**Mitigación**: Convertir LLM a advisor only, agregar validación estricta

#### RIESGO 2: Ausencia de Grounding obligatorio
**Severidad**: CRÍTICA
**Ubicación**: Todo el pipeline de ejecución
**Impacto**: El modelo puede alucinar información verificable
**Probabilidad**: ALTA
**Mitigación**: Implementar Grounding Engine en IntentEngine y ToolGateway

#### RIESGO 3: Exposición de información interna en UI
**Severidad**: ALTA
**Ubicación**: `src/components/Workbench/Workbench.tsx`
**Impacto**: Usuarios ven detalles internos que pueden confundir o exponer información sensible
**Probabilidad**: MEDIA
**Mitigación**: Implementar Presentation Layer y modo usuario/desarrollador

### 3.2 Riesgos Altos (requieren atención en corto plazo)

#### RIESGO 4: ModelRouter no considera hardware
**Severidad**: ALTA
**Ubicación**: `sentinel/core/model_router.py`
**Impacto**: Selección subóptima de modelos, posible degradación de performance
**Probabilidad**: MEDIA
**Mitigación**: Implementar Hardware Profiler y Model Capability Manager

#### RIESGO 5: MemoryBackend no tiene metadatos de confianza
**Severidad**: ALTA
**Ubicación**: `sentinel/core/operational_memory.py`
**Impacto**: Información almacenada sin validación de fuente o confianza
**Probabilidad**: MEDIA
**Mitigación**: Extender para soportar memoria confiable con metadata

#### RIESGO 6: DeepContextEngine no implementa descubrimiento real
**Severidad**: ALTA
**Ubicación**: `sentinel/core/deep_context.py`
**Impacto**: No hay aprendizaje del entorno, no hay detección de aplicaciones
**Probabilidad**: ALTA
**Mitigación**: Implementar Application Discovery Service

### 3.3 Riesgos Medios (requieren atención en mediano plazo)

#### RIESGO 7: Orchestrator tiene demasiadas dependencias
**Severidad**: MEDIA
**Ubicación**: `sentinel/core/orchestrator.py`
**Impacto**: Difícil de testear, mantener y extender
**Probabilidad**: MEDIA
**Mitigación**: Refactorizar para reducir acoplamiento, considerar patrón Facade

#### RIESGO 8: SentinelBridge mezcla lógica de negocio con API
**Severidad**: MEDIA
**Ubicación**: `sidecar/modules/sentinel_bridge.py`
**Impacto**: Violación de separación de responsabilidades
**Probabilidad**: MEDIA
**Mitigación**: Mover lógica de negocio a servicios dedicados

#### RIESGO 9: ContextEngine no sanitiza información sensible
**Severidad**: MEDIA
**Ubicación**: `sentinel/core/context.py`
**Impacto**: Posible exposición de información sensible
**Probabilidad**: BAJA
**Mitigación**: Implementar sanitización de datos sensibles

### 3.4 Riesgos Bajos (mejoras futuras)

#### RIESGO 10: ObservabilityService expone detalles internos
**Severidad**: BAJA
**Ubicación**: `sentinel/core/observability.py`
**Impacto**: Exposición de información técnica no necesaria para usuarios
**Probabilidad**: BAJA
**Mitigación**: Integrar con Presentation Layer

---

## 4. PUNTOS DE INTEGRACIÓN CLAVE

### 4.1 Puntos de Integración para Grounding Engine

#### PUNTO 1: IntentEngine → Grounding Engine
**Ubicación**: `sentinel/core/intent.py` después de detección de intent
**Propósito**: Detectar si el intent requiere información verificable
**Cambios requeridos**:
- Agregar campo `grounding_requirements` a `Intent`
- Llamar a `GroundingEngine.analyze_requirement()` después de clasificar intent
- Pasar requisitos al Orchestrator

#### PUNTO 2: ToolGateway → Grounding Engine
**Ubicación**: `sentinel/core/tool_gateway.py` antes de ejecutar herramienta
**Propósito**: Forzar obtención de datos desde fuente real
**Cambios requeridos**:
- Agregar parámetro `grounding_requirements` a `execute()`
- Validar grounding antes de ejecutar si es requerido
- Cachear resultados de grounding con TTL

#### PUNTO 3: ContextEngine → Grounding Engine
**Ubicación**: `sentinel/core/context.py` como fuente de datos
**Propósito**: Proporcionar datos verificados para grounding
**Cambios requeridos**:
- Agregar timestamp a todos los datos recopilados
- Implementar validación de frescura
- Sanitizar información sensible

### 4.2 Puntos de Integración para Presentation Layer

#### PUNTO 1: SentinelBridge → Presentation Layer
**Ubicación**: `sidecar/modules/sentinel_bridge.py` antes de responder
**Propósito**: Filtrar respuestas según modo usuario/desarrollador
**Cambios requeridos**:
- Envolver todas las respuestas con `PresentationLayer`
- Detectar modo desde configuración o header
- Filtrar campos internos según configuración de verbosidad

#### PUNTO 2: Workbench → Presentation Layer
**Ubicación**: `src/components/Workbench/Workbench.tsx`
**Propósito**: UI diferenciada según modo
**Cambios requeridos**:
- Agregar selector de modo usuario/desarrollador
- Condicionalmente renderizar detalles internos
- Usar API filtrada según modo

#### PUNTO 3: ObservabilityService → Presentation Layer
**Ubicación**: `sentinel/core/observability.py`
**Propósito**: Filtrar métricas según modo
**Cambios requeridos**:
- Agregar métodos para diferentes niveles de detalle
- Integrar con VerbosityConfig

### 4.3 Puntos de Integración para Decision Engine Seguro

#### PUNTO 1: DecisionEngine → LLM Advisor
**Ubicación**: `sentinel/core/decision_engine.py`
**Propósito**: Convertir LLM de autoridad a advisor
**Cambios requeridos**:
- Crear `LLMDecisionAdvisor` como componente separado
- Implementar validación estricta de salida del LLM
- Hacer que el LLM sea opcional (fallback a evaluación objetiva)

#### PUNTO 2: SimulationEngine → Decision Engine
**Ubicación**: `sentinel/core/simulation.py` → `decision_engine.py`
**Propósito**: Usar simulación como fuente de datos objetivos
**Cambios requeridos**:
- Mejorar detección de acciones peligrosas en simulación
- Priorizar evaluación objetiva sobre advice del LLM
- Registrar incertidumbre en decisiones

#### PUNTO 3: Confirmation → Risk Assessment
**Ubicación**: `sentinel/core/confirmation.py`
**Propósito**: Integrar con evaluación de riesgo mejorada
**Cambios requeridos**:
- Usar `requires_confirmation` de RiskAssessment
- Mostrar factores de riesgo al usuario
- Integrar con Presentation Layer para formateo

### 4.4 Puntos de Integración para Application Discovery

#### PUNTO 1: DeepContextEngine → Application Discovery
**Ubicación**: `sentinel/core/deep_context.py`
**Propósito**: Implementar descubrimiento real de aplicaciones
**Cambios requeridos**:
- Implementar `app_discovery_fn` usando `ApplicationDiscoveryService`
- Almacenar resultados en KnowledgeBase
- Detectar cambios entre ejecuciones

#### PUNTO 2: KnowledgeBase → App Profiles
**Ubicación**: `sentinel/core/knowledge_base.py`
**Propósito**: Almacenar perfiles de aplicaciones
**Cambios requeridos**:
- Extender esquema para soportar `AppProfile`
- Implementar indexado por nombre, ruta, capacidades
- Agregar TTL para invalidación

#### PUNTO 3: Planner → Application Discovery
**Ubicación**: `sentinel/core/planner.py`
**Propósito**: Usar conocimiento de aplicaciones para planes inteligentes
**Cambios requeridos**:
- Integrar con `ApplicationDiscoveryService.resolve_app_intent()`
- Usar capacidades conocidas para generar planes
- Fallback a comportamiento actual si no hay conocimiento

### 4.5 Puntos de Integración para Model Capability Manager

#### PUNTO 1: Orchestrator → Hardware Profiler
**Ubicación**: `sentinel/core/orchestrator.py` en `__init__`
**Propósito**: Analizar hardware al iniciar
**Cambios requeridos**:
- Inicializar `HardwareProfiler` al arrancar
- Generar `DeviceProfile` una vez por sesión
- Pasar perfil a ModelRouter

#### PUNTO 2: ModelRouter → Model Capability Manager
**Ubicación**: `sentinel/core/model_router.py`
**Propósito**: Seleccionar modelos según hardware
**Cambios requeridos**:
- Integrar con `ModelCapabilityManager`
- Usar `DeviceProfile` para filtrar modelos disponibles
- Optimizar configuración según hardware

#### PUNTO 3: ProviderSpec → Hardware Requirements
**Ubicación**: `sentinel/core/model_router.py`
**Propósito**: Agregar metadata de requisitos hardware
**Cambios requeridos**:
- Extender `ProviderSpec` con requisitos hardware
- Agregar campos para min RAM, min VRAM, aceleración soportada
- Validar requisitos antes de seleccionar modelo

### 4.6 Puntos de Integración para Reliable Memory

#### PUNTO 1: MemoryBackend → Memory Metadata
**Ubicación**: `sentinel/core/operational_memory.py`
**Propósito**: Extender para soportar metadata de confianza
**Cambios requeridos**:
- Agregar `MemoryMetadata` a todas las entradas
- Implementar separación por tipos de memoria
- Agregar mecanismo de invalidación

#### PUNTO 2: KnowledgeBase → Reliable Memory
**Ubicación**: `sentinel/core/knowledge_base.py`
**Propósito**: Integrar con sistema de confianza
**Cambios requeridos**:
- Usar `ReliableMemory` como backend
- Validar confianza antes de retornar conocimiento
- Implementar invalidación por TTL

#### PUNTO 3: Orchestrator → Reliable Memory
**Ubicación**: `sentinel/core/orchestrator.py`
**Propósito**: Usar memoria con metadatos de confianza
**Cambios requeridos**:
- Reemplazar acceso directo a memoria con `ReliableMemory`
- Pasar metadata al almacenar
- Validar confianza al recuperar

---

## 5. ANÁLISIS DE COMPATIBILIDAD

### 5.1 Interfaces Públicas Actuales

#### Orchestrator.process()
**Firma**: `async def process(utterance: str, *, identity: Optional[dict] = None, session_id: Optional[str] = None, dry_run: bool = False, skip_simulation: bool = False, override_plan: Optional[Plan] = None, timeout: Optional[float] = None) -> ExecutionResult`
**Estado**: ✅ **ESTABLE** - No se planea cambiar firma
**Cambios planeados**: Agregar parámetros opcionales para presentación y grounding

#### ToolGateway.execute()
**Firma**: `async def execute(tool_id: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult`
**Estado**: ✅ **ESTABLE** - No se planea cambiar firma
**Cambios planeados**: Agregar parámetros opcionales para grounding

#### IntentEngine.parse()
**Firma**: `def parse(self, utterance: str, context: Optional[Dict[str, Any]] = None) -> Intent`
**Estado**: ✅ **ESTABLE** - No se planea cambiar firma
**Cambios planeados**: Extender `Intent` con campos opcionales

#### DecisionEngine.evaluate()
**Firma**: `def evaluate(self, plan: Plan, context: Optional[Dict[str, Any]] = None) -> DecisionResult`
**Estado**: ✅ **ESTABLE** - No se planea cambiar firma
**Cambios planeados**: Cambios internos, interfaz pública mantenida

### 5.2 Estructuras de Datos Actuales

#### Intent
**Campos actuales**: `action`, `target`, `parameters`, `confidence`, `raw_input`
**Cambios planeados**: Agregar `grounding_requirements` (opcional)
**Compatibilidad**: ✅ **COMPATIBLE** - Campo opcional, código existente ignora

#### ExecutionResult
**Campos actuales**: Múltiples campos incluyendo `plan`, `decision`, `tool_result`, `advisory`
**Cambios planeados**: Ninguno a estructura existente
**Compatibilidad**: ✅ **COMPATIBLE** - Sin cambios a campos existentes

#### ToolResult
**Campos actuales**: `success`, `data`, `error`, `tool_id`, `execution_id`, `duration_ms`, `timestamp`, `requires_confirmation`, `policy_decision`, `policy_result`, `quality_result`
**Cambios planeados**: Agregar `grounding_metadata` (opcional)
**Compatibilidad**: ✅ **COMPATIBLE** - Campo opcional

### 5.3 API HTTP Actual

#### POST /v1/execute
**Estado**: ✅ **ESTABLE** - No se planea cambiar endpoint
**Cambios planeados**: Filtrar respuesta con Presentation Layer
**Compatibilidad**: ✅ **COMPATIBLE** - Cambio en contenido, no en estructura

#### POST /v1/confirm
**Estado**: ✅ **ESTABLE** - No se planea cambiar
**Cambios planeados**: Ninguno
**Compatibilidad**: ✅ **COMPATIBLE**

#### POST /sentinel/conversation (streaming)
**Estado**: ✅ **ESTABLE** - No se planea cambiar endpoint
**Cambios planeados**: Filtrar eventos con Presentation Layer
**Compatibilidad**: ✅ **COMPATIBLE** - Cambio en contenido, no en estructura

---

## 6. RECOMENDACIONES DE IMPLEMENTACIÓN

### 6.1 Estrategia de Implementación

#### FASE 2: Grounding Engine (Semanas 1-3)
**Prioridad**: CRÍTICA
**Orden**:
1. Crear `sentinel/core/grounding.py` (nuevo componente)
2. Extender `Intent` con `grounding_requirements`
3. Integrar en `IntentEngine`
4. Integrar en `ToolGateway`
5. Tests y documentación

**Riesgo**: Bajo - componente nuevo, sin cambios a existentes
**Rollback**: Remover integración, mantener código nuevo para futuro uso

#### FASE 3: Presentation Layer (Semanas 4-5)
**Prioridad**: CRÍTICA
**Orden**:
1. Crear `sentinel/core/presentation.py` (nuevo componente)
2. Crear configuración de modo (`sentinel/core/mode_config.py`)
3. Integrar en `SentinelBridge`
4. Integrar en `Workbench`
5. Tests y documentación

**Riesgo**: Medio - cambios en capa de API y UI
**Rollback**: Remover wrapper de Presentation Layer, mantener comportamiento anterior

#### FASE 4: Decision Engine Seguro (Semanas 6-7)
**Prioridad**: CRÍTICA
**Orden**:
1. Crear `LLMDecisionAdvisor` (nuevo componente)
2. Crear `LLMOutputValidator` (nuevo componente)
3. Refactorizar `DecisionEngine` para usar advisor pattern
4. Mejorar `SimulationEngine` como fuente objetiva
5. Tests exhaustivos y comparación con comportamiento anterior

**Riesgo**: Alto - cambios en componente crítico de seguridad
**Rollback**: Revertir a versión anterior de DecisionEngine, mantener nuevos componentes

#### FASE 5: Environmental Learning (Semanas 8-10)
**Prioridad**: ALTA
**Orden**:
1. Crear `sentinel/services/app_discovery.py` (nuevo servicio)
2. Crear `sentinel/services/app_knowledge.py` (nuevo servicio)
3. Extender `KnowledgeBase` para soportar AppProfile
4. Implementar `app_discovery_fn` en `DeepContextEngine`
5. Integrar en `Planner`
6. Tests y documentación

**Riesgo**: Medio - nuevos servicios, integración con existentes
**Rollback**: Deshabilitar hooks de descubrimiento, mantener comportamiento anterior

#### FASE 6: Hardware Intelligence (Semanas 11-12)
**Prioridad**: ALTA
**Orden**:
1. Crear `sentinel/core/hardware_profiler.py` (nuevo componente)
2. Crear `sentinel/core/model_capability.py` (nuevo componente)
3. Extender `ProviderSpec` con requisitos hardware
4. Integrar en `Orchestrator` (inicialización)
5. Integrar en `ModelRouter` (selección)
6. Tests y documentación

**Riesgo**: Medio - nuevos componentes, integración con existentes
**Rollback**: Remover integración, mantener selección de modelos anterior

#### FASE 7: Reliable Memory (Semanas 13-14)
**Prioridad**: ALTA
**Orden**:
1. Crear `sentinel/core/reliable_memory.py` (nuevo componente)
2. Extender `MemoryBackend` para soportar metadata
3. Integrar en `KnowledgeBase`
4. Integrar en `Orchestrator`
5. Migración de datos existentes
6. Tests y documentación

**Riesgo**: Alto - cambios en sistema de almacenamiento
**Rollback**: Revertir a versión anterior de MemoryBackend, mantener nueva estructura

### 6.2 Estrategia de Testing

#### Unit Tests (70%)
- Tests de componentes nuevos aislados
- Tests de funciones puras y validación
- Tests de integración de componentes individuales

#### Integration Tests (20%)
- Tests de flujos completos con componentes reales
- Tests de API con componentes mockeados
- Tests de integración entre capas

#### E2E Tests (10%)
- Tests de flujos de usuario completos
- Tests de modo usuario vs. desarrollador
- Tests de escenarios críticos de seguridad

**Coverage Goal**: 80% mínimo para componentes críticos

### 6.3 Estrategia de Rollout

#### Beta Interna (2 semanas)
- Despliegue en ambiente de desarrollo
- Equipo interno prueba características
- Feedback y ajustes

#### Beta Externa (4 semanas)
- Despliegue a grupo de usuarios beta
- Recopilación de feedback
- Ajustes basados en feedback

#### Lanzamiento Gradual (6 semanas)
- Rollout progresivo a usuarios
- Monitoreo de métricas
- Rollback planificado si es necesario

---

## 7. MÉTRICAS DE ÉXITO

### 7.1 Métricas Técnicas
- Coverage de tests: >80% para componentes críticos
- Performance: <500ms para operaciones de grounding
- Disponibilidad: >99.5% durante rollout
- Bug rate: <5 bugs críticos por sprint

### 7.2 Métricas de Seguridad
- Incidentes de seguridad: 0 incidentes nuevos
- Vulnerabilidades: 0 vulnerabilidades críticas introducidas
- Penetration tests: Pasar todos los tests existentes

### 7.3 Métricas de Usuario
- Satisfacción: >4/5 en encuestas de usuarios beta
- Adopción: >70% de usuarios activan modo desarrollador apropiadamente
- Soporte: <20% de tickets relacionados con nuevos features

---

## 8. CONCLUSIONES

### 8.1 Estado Actual de la Arquitectura

**Fortalezas**:
- ✅ Separación clara de responsabilidades en áreas clave
- ✅ Componentes de seguridad bien diseñados (PolicyEngine, QualityGate, ToolGateway)
- ✅ Infraestructura de orquestación robusta (Orchestrator, Planner)
- ✅ Sistema de advisory correctamente separado (AdvisoryService)
- ✅ Sistema de recuperación bien implementado
- ✅ Observabilidad completa

**Debilidades Críticas**:
- ❌ DecisionEngine usa LLM con autoridad (riesgo de seguridad)
- ❌ Ausencia de Grounding obligatorio (riesgo de alucinaciones)
- ❌ Exposición de información interna en UI (riesgo de privacidad/UX)
- ❌ ModelRouter no considera hardware (performance subóptimo)
- ❌ MemoryBackend no tiene metadata de confianza (confiabilidad)
- ❌ DeepContextEngine no implementa descubrimiento real (sin aprendizaje)

**Debilidades Medias**:
- ⚠️ Orchestrator tiene demasiadas dependencias (mantenibilidad)
- ⚠️ SentinelBridge mezcla lógica de negocio (separación de responsabilidades)
- ⚠️ ContextEngine no sanitiza información sensible (privacidad)

### 8.2 Recomendaciones Inmediatas

1. **Priorizar FASE 2 (Grounding Engine)**: Reducir alucinaciones es crítico
2. **Priorizar FASE 3 (Presentation Layer)**: Separación usuario/desarrollador es urgente
3. **Priorizar FASE 4 (Decision Engine Seguro)**: Riesgo de seguridad crítico
4. **Mantener compatibilidad**: Todos los cambios propuestos son aditivos o refactorizaciones internas
5. **Testing exhaustivo**: Invertir tiempo significativo en tests, especialmente para DecisionEngine

### 8.3 Impacto Esperado

Implementando este plan de migración, se espera:
- **Reducción del 90%** en riesgos de alucinaciones mediante grounding
- **Mejora del 80%** en experiencia de usuario mediante modos diferenciados
- **Reducción del 70%** en exposición de información sensible
- **Mejora del 60%** en selección de modelos mediante hardware profiling
- **Mejora del 50%** en confianza del sistema mediante memoria confiable

---

## 9. PRÓXIMOS PASOS

Para proceder a FASE 2 (Grounding Engine), se requiere:

1. ✅ **APROBACIÓN DE ESTE DOCUMENTO**: Revisar y aprobar este ARCHITECTURE_REVIEW.md
2. **PRIORIZACIÓN DE FASE 2**: Confirmar que Grounding Engine es la siguiente fase
3. **CONFIGURACIÓN DE AMBIENTE**: Preparar ambiente de desarrollo para nuevos componentes
4. **DEFINICIÓN DE MÉTRICAS**: Establecer métricas y monitoreo para el rollout
5. **BEGIN FASE 2**: Comenzar implementación de Grounding Engine

---

**DOCUMENTO ARCHITECTURE_REVIEW.md COMPLETADO**

Este documento proporciona un análisis completo de la arquitectura existente de Sentinel, identificando componentes, dependencias, riesgos y puntos de integración clave para la evolución planificada hacia una plataforma de confianza y orquestación de IA.

**ESTADO**: Listo para revisión y aprobación antes de proceder a FASE 2.
