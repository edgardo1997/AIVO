# Auditoría Orientada a la Visión — Sentinel

> **Fecha:** 2026-07-17  
> **Propósito:** Evaluar el código base actual contra la visión completa del producto definida en `CONSTITUTION.md`, `docs/VISION_COMPLETA_SENTINEL.md`, `SENTINEL_MASTER_ARCHITECTURE_REVIEW.md`, y `sentinel/docs/PRODUCT_IDENTITY.md`.
> **Metodología:** Cada sección contrasta una promesa/responsabilidad de la visión con el estado real del código.

---

## 0. Resumen Ejecutivo

| Dimensión | Estado |
|-----------|--------|
| **Pipeline obligatorio** | ✅ Estructuralmente presente, parcialmente integrado |
| **Grounding** | 🟡 Implementado pero no integrado en gateway |
| **Decision Engine** | 🟡 Advisor Pattern implementado, LLM aún tiene influencia indirecta |
| **Presentation Layer** | 🟡 Existe y se usa en API, no en orchestrator |
| **Hardware Intelligence** | ✅ Integrado con ModelRouter |
| **Application Knowledge** | 🟡 Alimenta DeepContext, no al Planner |
| **Environmental Learning** | 🟡 Inyecta contexto pasivo, no afecta decisiones |
| **Memoria Confiable** | ❌ No existe con metadata/confianza |
| **No-bypass** | ⚠️ `execute_direct` omite partes del pipeline |
| **UI alineada con Trust Layer** | ❌ UI tipo dashboard, no centrada en pipeline |
| **Tests vs. visión** | 🟡 1,834 tests pero no cubren flujos críticos de confianza |
| **Madurez arquitectónica** | 4.9/10 (autoevaluación) |

**Fase actual:** Fase 2 completada (tests deterministas), código de Fase 3-7 escrito pero NO integrado en el pipeline principal. El proyecto tiene los **bloques de construcción** pero **no el sistema integrado** que la visión describe.

---

## 1. Identidad del Producto

### Lo que Sentinel DEBE ser (según la visión)
> "Sentinel es un **orquestador inteligente local** cuyo núcleo es una **Trust Layer obligatoria** para controlar, proteger, explicar y auditar toda interacción entre inteligencias artificiales, herramientas y el sistema operativo."

### Lo que el código actual ES
- **Sí es**: Un backend FastAPI con 198 endpoints, un frontend React de 27 tabs, un pipeline de 7 pasos en `orchestrator.py`
- **Sí es**: Una plataforma multi-provider con 73 tools registradas
- **No es todavía**: Una Trust Layer integrada donde CADA interacción pase por el pipeline completo

### Gap fondamental
La visión dice "toda interacción". El `execute_direct()` en `orchestrator.py:648` omite: grounding, deep context, simulación, y advisory. Cualquier tool registrada puede ejecutarse sin pasar por la validación completa.

---

## 2. Pipeline Obligatorio

### Visión
```
Identidad → Intención → Decisión → Política → Gateway → Ejecución → Calidad → Auditoría → Advisory

Cada etapa es obligatoria. No existen rutas de escape.
```

### Realidad en `orchestrator._process_impl()` (líneas 275-646)

| Etapa | Estado | Dónde |
|-------|--------|-------|
| ✅ Identidad | Inyectada en context si se provee | línea 293 |
| ✅ Contexto | ContextEngine + DeepContextEngine | líneas 343-418 |
| ✅ Intención | IntentEngine.parse() + grounding attach | líneas 427-436 |
| ✅ Plan | Planner.plan() + PlanCache | líneas 438-445 |
| ✅ Simulación | SimulationEngine.simulate() | líneas 458-476 |
| ✅ Decisión | DecisionEngine.evaluate() | líneas 478-496 |
| ✅ Política | PolicyEngine (dentro de ToolGateway) | vía tool_gateway.execute() |
| ✅ Gateway | ToolGateway.execute() | línea 946 |
| ✅ Ejecución | _execute_single_step() | líneas 902-1055 |
| ✅ Calidad | QualityGate (dentro de ToolGateway) | vía tool_gateway.execute() |
| ✅ Auditoría | _store_memory() + audit_service | líneas 801-877 |
| 🟡 Advisory | _attach_advisory() al final | línea 791-799 |

**Problemas:**
1. **Simulación se ejecuta pero su resultado no alimenta al DecisionEngine**. El `simulation_result` se guarda en context pero `DecisionEngine.evaluate()` no lo usa como input estructurado.
2. **Grounding se verifica post-execución** pero no preventivamente. `_verify_grounding_results()` (línea 628) revisa después de ejecutar, no antes.
3. **Advisory se adjunta al final pero no hay retroalimentación al usuario** en la UI.
4. **Presentation Layer no se llama** en `_attach_advisory()`. El resultado se devuelve raw.

---

## 3. Grounding (Fase 2)

### Visión
> "Si existe una fuente verificable para una pregunta, LA HERRAMIENTA TIENE PRIORIDAD SOBRE EL MODELO."

### Realidad
- ✅ `GroundingEngine` (383 líneas) implementado en `sentinel/core/grounding.py`
- ✅ Detecta 6 categorías de información verificable
- ✅ Cache con TTL y frescura
- ✅ Integrado con IntentEngine vía `intent_engine.attach_grounding()` (orchestrator línea 428-429)
- ✅ Verificación post-ejecución vía `_verify_grounding_results()` (línea 628)
- ❌ **NO está integrado en ToolGateway** — el gateway no consulta al GroundingEngine antes de ejecutar
- ❌ **NO hay priorización de herramientas sobre el modelo** — el planner puede elegir modelo incluso si existe herramienta verificable
- ❌ **NO hay fallback automático**: si el grounding falla, no se reintenta con herramienta alternativa

**Tests:** `tests/test_grounding.py` existe pero es mínimo.

---

## 4. Decision Engine (Fase 4 parcial)

### Visión
> "NINGÚN MODELO DE IA TIENE AUTORIDAD DIRECTA SOBRE EL SISTEMA. El LLM solo aconseja, nunca decide."

### Realidad
- ✅ `ObjectiveRiskAssessor` (198 líneas) evalúa riesgo objetivo SIN LLM
- ✅ `LLMDecisionAdvisor` (167 líneas) implementa el patrón "advisor, no authority"
- ✅ `LLMOutputValidator` usado para validar salida del advisor
- 🟡 `DecisionEngine.evaluate()` (línea 83-308) llama a AMBOS: `objective_assessor.assess()` Y `llm_advisor.advise()`
- 🟡 El `final_risk_score` combina factores objetivos con recomendación del LLM
- ⚠️ **La influencia del LLM no es cero**: si el advisor sugiere "high risk" con confianza 0.9, el score final se incrementa
- ❌ **No hay registro de cuánto influyó el LLM vs factores objetivos** — viola el principio de explicabilidad

**Análisis de `decision_engine.py` líneas 156-169:**
```python
if advisory_result.used_llm:
    if advisory_result.risk_recommendation in ("high", "critical"):
        objective_result.final_risk += 0.2  # LLM infla riesgo
```
La influencia del LLM es acotada (+0.2) pero NO es cero. La visión exige que el LLM tenga 0 autoridad.

---

## 5. Presentation Layer (Fase 3)

### Visión
> "Separar experiencia de usuario normal y experiencia avanzada de desarrollador. El usuario no debería ver scores de riesgo, tool_ids ni detalles técnicos."

### Realidad
- ✅ `PresentationLayer` (214 líneas) implementado en `sentinel/presentation.py`
- ✅ Dos modos: `USER` y `DEVELOPER`
- ✅ Oculta `final_risk_score` en modo USER
- ✅ Oculta `tool_id` en modo USER
- ✅ Oculta `details` en modo USER
- ✅ Integrado en `sidecar/modules/sentinel_bridge.py` (línea 16, 21)
- ✅ Tests en `tests/test_presentation.py`
- ❌ **NO integrado en el orchestrator**: `_attach_advisory()` (línea 791) solo llama al advisory service, no al presentation layer
- ❌ **NO usado en el frontend**: el componente `Workbench.tsx` recibe datos raw, no presentados
- ❌ **No hay modo DEVELOPER seleccionable en la UI**

---

## 6. Application Knowledge (Fase 5)

### Visión
> "Sentinel debe saber qué aplicaciones existen en el sistema y cómo funcionan para planificar inteligentemente."

### Realidad
- ✅ `ApplicationKnowledgeService` (218 líneas) implementado
- ✅ Cache TTL configurable
- ✅ Filtrado de campos sensibles (executable paths ocultos por defecto)
- ✅ Descubrimiento desde el sistema (Start Menu, PATH, installed apps)
- ✅ Tests en `sidecar/tests/test_application_knowledge.py`
- ✅ Integrado en DeepContextEngine vía `_get_apps()` en `sidecar/modules/__init__.py:75-78`
- ✅ Usado en executor_service para lookup de apps
- ❌ **NO integrado en Planner**: el planner no recibe perfiles de aplicaciones
- ❌ **NO usado en ModelRouter**: no influye en selección de modelo
- ❌ **No hay UI de Application Knowledge** en el frontend

---

## 7. Hardware Intelligence (Fase 6)

### Visión
> "Sentinel debe conocer el hardware disponible para elegir modelos locales vs remotos, estimar capacidad de procesamiento y optimizar recursos."

### Realidad
- ✅ `HardwareProfiler` (293 líneas) implementado
- ✅ Detecta CPU (físicos/lógicos), RAM, GPUs (NVIDIA/AMD/Intel), NPU
- ✅ Integrado con `ModelRouter` vía `HardwareProfile.from_context()` y `ModelCapabilityManager`
- ✅ `to_routing_context()` expone capacidades sin identificadores de hardware
- ✅ Integrado en DeepContextEngine vía `_get_hardware()`
- ✅ Tests en `sidecar/tests/test_hardware_intelligence.py`
- 🟡 **ModelRouter usa hardware profile para decidir capacidad local, pero no hay decisión automática local vs remoto**
- ❌ **No hay UI de hardware profile** en el frontend

---

## 8. Environmental Learning (Fase 7)

### Visión
> "Sentinel debe aprender del entorno sin invadir privacidad, detectando cambios en aplicaciones, hardware y uso para adaptar su comportamiento."

### Realidad
- ✅ `EnvironmentLearningService` + `ChangeDetector` (248 líneas) implementado
- ✅ Detecta cambios en apps instaladas y hardware
- ✅ Retención configurable (90 días)
- ✅ Integrado en orchestrator (línea 409-418) vía `_environment_learning.observe()`
- ✅ Solo consume datos de ApplicationKnowledge + HardwareProfile (no inspecciona la máquina)
- ❌ **Los cambios detectados NO afectan decisiones** — solo se inyectan como contexto pasivo
- ❌ **No hay UI de cambios ambientales**
- ⚠️ El contexto inyectado (`context["environment_changes"]`) no es usado por DecisionEngine ni Planner

---

## 9. Confiable Memory (Fase 4 core)

### Visión
> "La memoria debe ser recuperable, inspeccionable, aislada por identidad y eliminable. Debe incluir metadatos, confianza y fuente."

### Realidad
- ✅ `Memory` (205 líneas) — KV store, snapshots, sesiones, preferencias
- ✅ `OperationalMemory` (1,213 líneas) — records de ejecución, acciones pendientes, memoria episódica, patrones aprendidos
- ✅ `SQLiteBackend` — persistencia con TTL y evicción
- ✅ Record Store con metadata de sesión + identidad
- ❌ **No hay "Reliable Memory" con metadata de confianza** como describe la visión
- ❌ **No hay confidence scores por ítem de memoria**
- ❌ **No hay separación clara entre**: contexto temporal / memoria de sesión / preferencias / historial / conocimiento incorporado
- ❌ **No hay UI de Memory con confianza/metadata**

---

## 10. Advisory & Confidence

### Visión
> "Sentinel Advisory & Confidence analiza resultados ya producidos y comunica nivel de confianza razonado, fuentes, contradicciones, riesgos y alternativas. No ejecuta herramientas ni cambia planes."

### Realidad
- ✅ `sentinel/advisory/` — módulo completo con 5 archivos (confidence.py, config.py, models.py, rules.py, service.py)
- ✅ `AdvisoryService.analyze()` produce niveles de intervención (0-3)
- ✅ Integrado en orchestrator vía `_attach_advisory()`
- ✅ `AdvisoryNotice.tsx` en el frontend
- ✅ Tests en `tests/test_advisory.py`
- 🟡 La UI muestra advisory pero no está integrada en el flujo de usuario (no bloquea, solo informa)
- 🟡 Advisory es post-ejecución, no hay "advisory preventivo" que la visión describe

---

## 11. Frontend vs. Visión

### Visión
> "Sentinel puede conversar porque el lenguaje natural es una interfaz útil, pero conversar no es su propósito principal."

### Realidad
- ✅ 27 tabs cubriendo: Chat, Sentinel, Execute, Console, Files, Fleet, Plugins, Agents, Triggers, Permissions, Policies, Audit, Profile, Settings, Observability, FeedbackCosts, Vault, KnowledgeBase, Reports, Memory, Alertas, Admin, Help, Proactive, Monitor, Dashboard
- ✅ Componentes: Sidebar, ErrorBoundary, ConnectionStatus, Toast, Loading, EmptyState, UserBadge
- ✅ Login/Onboarding flow
- ⚠️ **La UI está organizada como dashboard de administración, no como Trust Layer**
  - El componente principal es `Workbench.tsx` (47KB, 43 sub-componentes)
  - No hay un "centro de confianza" que muestre el pipeline en acción
  - Las confirmaciones de seguridad (`SimulationConfirmDialog`, `ConfirmDialog`) existen pero no son obligatorias
- ❌ **No hay visualización del pipeline**: el usuario no ve qué etapa se está ejecutando
- ❌ **No hay visualización de grounding**: no se muestra qué info es verificada vs generada
- ❌ **No hay visualización del risk score** (incluso en modo developer)
- ❌ **No hay progresión USER → DEVELOPER mode**

---

## 12. Tests vs. Visión

### Visión
> "El sistema debe ser verificable, con tests que garanticen que el pipeline no tiene rutas de escape y que los principios de confianza se cumplen."

### Realidad
| Tipo | Cantidad | Cobertura de visión |
|------|----------|---------------------|
| Backend (sidecar/tests/) | 85 files | 🟡 Cubren servicios pero NO integración del pipeline completo |
| Frontend (src/__tests__/) | 27 files | 🟡 Cubren componentes UI pero NO flujos de confianza |
| Raíz (tests/) | 5 files | ✅ Tests específicos de visión (grounding, decision engine, presentation) |
| **Total** | **~1,834** | |

**Tests existentes para la visión:**
- `tests/test_decision_engine_seguro.py` — ✅ Verifica que LLM no tenga autoridad
- `tests/test_grounding.py` — ✅ Tests de grounding
- `tests/test_presentation.py` — ✅ Tests de presentation layer
- `tests/test_advisory.py` — ✅ Tests de advisory
- `sidecar/tests/test_trust_pipeline_invariants.py` — ✅ Invariantes del pipeline

**Tests FALTANTES para la visión:**
- ❌ No hay test que verifique que `execute_direct()` NO omite partes del pipeline
- ❌ No hay test que verifique que el `simulation_result` alimenta al DecisionEngine
- ❌ No hay test que verifique que el grounding previene ejecución sin datos verificables
- ❌ No hay test E2E que ejecute el pipeline completo y verifique cada etapa

---

## 13. Arquitectura vs. Visión: Mapa de Implementación

```
Visión                                        Estado
──────────────────────────────────────────────────────────────
Pipeline obligatorio completo                 🟡 7/9 etapas integradas
Grounding en gateway                          ❌ No integrado
LLM como advisor, no authority                🟡 Influencia reducida pero no cero
Presentation Layer en pipeline                ❌ Solo en API, no en orchestrator
Application Knowledge en Planner              ❌ Solo en DeepContext
Hardware Intelligence en ModelRouter          ✅ Integrado
Environmental Learning activo                 ❌ Solo contexto pasivo
Reliable Memory con confianza                 ❌ No existe
Advisory preventivo                           🟡 Solo post-ejecución
UI de Trust Layer                             ❌ UI tipo dashboard
Sin rutas de escape                           ⚠️ execute_direct() omite etapas
```

---

## 14. Hallazgos Críticos

### 🔴 CRÍTICO: `execute_direct()` omite etapas del pipeline
**Archivo:** `sentinel/core/orchestrator.py:648`
**Problema:** Omite grounding, deep context, simulación, advisory. Cualquier tool puede ejecutarse sin validación completa.
**Impacto:** Viola el principio "No bypass" de la Constitución.

### 🔴 CRÍTICO: Presentation Layer no está en el pipeline
**Archivo:** `sentinel/presentation.py` (existe) vs `sentinel/core/orchestrator.py:791`
**Problema:** El orchestrator devuelve `ExecutionResult` raw. La presentación solo ocurre en la API.
**Impacto:** El frontend recibe datos técnicos que deberían filtrarse. No hay separación USER vs DEVELOPER.

### 🔴 CRÍTICO: Decision Engine aún da influencia al LLM
**Archivo:** `sentinel/core/decision_engine.py:156-169`
**Problema:** El LLM advisor puede modificar el risk score final en +0.2
**Impacto:** Un LLM comprometido o con alucinaciones puede influir en decisiones de seguridad.

### 🟡 ALTO: Grounding no preventivo
**Archivo:** `sentinel/core/orchestrator.py:628,1058-1068`
**Problema:** Grounding se verifica POST-ejecución. Si falla, el daño ya ocurrió.
**Impacto:** Información no verificable puede ejecutarse antes de ser detectada.

### 🟡 ALTO: UI no refleja la Trust Layer
**Archivo:** `src/components/Workbench/Workbench.tsx`
**Problema:** 27 tabs tipo dashboard, no hay visualización del pipeline.
**Impacto:** El usuario no puede ver qué etapa se ejecuta, qué riesgos se evaluaron, qué información está grounded.

### 🟡 ALTO: Environmental Learning es pasivo
**Archivo:** `sentinel/core/orchestrator.py:409-418`
**Problema:** Los cambios detectados se inyectan como contexto pero no afectan decisiones.
**Impacto:** El sistema "aprende" pero no actúa sobre lo aprendido.

### 🟡 MEDIO: No hay Reliable Memory con confianza
**Problema:** OperationalMemory tiene records pero sin confidence scores por ítem.
**Impacto:** No se puede distinguir información de alta vs baja confianza.

### 🟡 MEDIO: Application Knowledge no alimenta al Planner
**Archivo:** `sentinel/core/application_knowledge.py` vs `sentinel/core/planner.py`
**Problema:** Planner genera planes sin conocer apps instaladas.
**Impacto:** Planes pueden sugerir acciones para apps que no existen.

---

## 15. Bloqueadores para v1.0

Para que Sentinel sea fiel a su visión, estos items deben resolverse ANTES de considerar el producto completo:

1. **`execute_direct()` debe integrar el pipeline completo** — o eliminarse
2. **PresentationLayer debe integrarse en `_attach_advisory()`** — para que el frontend reciba datos presentados
3. **DecisionEngine debe tener 0 influencia del LLM** — el advisor solo debe aconsejar, nunca modificar scores
4. **GroundingEngine debe integrarse en ToolGateway** — para prevenir ejecución sin datos verificables
5. **UI debe mostrar el pipeline de confianza** — al menos indicador de etapa actual

---

## 16. Fortalezas (Lo que SÍ está alineado con la visión)

1. ✅ **Pipeline de 7 pasos**: Identity → Intent → Plan → Decision → Gateway → Execution → Audit existe y es funcional
2. ✅ **73 tools registradas** con gateway centralizado — sin acceso directo a herramientas
3. ✅ **ObjectiveRiskAssessor** sin LLM — evaluación objetiva de riesgo
4. ✅ **LLMDecisionAdvisor** como advisor separado — arquitectura correcta aunque con fuga
5. ✅ **GroundingEngine** completo con categorías, TTL, caché — solo falta integración
6. ✅ **Hardware Intelligence** integrada con ModelRouter
7. ✅ **Application Knowledge Service** con descubrimiento real del sistema
8. ✅ **PresentationLayer** con modo USER/DEVELOPER — implementación correcta, solo falta integración
9. ✅ **Advisory & Confidence** módulo completo — el más alineado con la visión
10. ✅ **Conversation availability** (conversation/) — responde sin LLM cuando no hay modelos
11. ✅ **JWT + Windows ACL** — seguridad a nivel OS
12. ✅ **1,834 tests** — base sólida para expandir
13. ✅ **No telemetry, local-first** — principios de privacidad intactos

---

## 17. Próximos Pasos Recomendados

### Inmediatos (Semana 1-2)
1. **Eliminar influencia del LLM en DecisionEngine** — que el advisor solo produzca advertencias, no modifique scores
2. **Integrar PresentationLayer en orchestrator** — que `_attach_advisory()` use `PresentationLayer.present()`
3. **Añadir validación en `execute_direct()`** — al menos deep context + grounding

### Corto plazo (Semana 3-4)
4. **Integrar GroundingEngine en ToolGateway** — verificar antes de ejecutar
5. **Conectar ApplicationKnowledge con Planner** — inyectar perfiles de apps
6. **Hacer Environmental Learning activo** — que los cambios afecten decisiones (ej: "app X ya no está instalada")

### Mediano plazo (Mes 2)
7. **Implementar Reliable Memory con confidence scores**
8. **Rediseñar UI como Trust Layer** — pipeline visible, modo USER/DEVELOPER
9. **Tests E2E del pipeline completo** — sin rutas de escape

### Largo plazo (Mes 3+)
10. **Simulation → DecisionEngine feedback loop** — que simulación alimente decisiones
11. **UI de grounding evidence** — mostrar qué info es verificada
12. **Modo DEVELOPER en frontend** — toggle para ver detalles técnicos
