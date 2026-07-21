# Fases de Trabajo — Sentinel

> Cada fase es auto-contenida, verificable y termina con `git commit`.  
> No avanzo a la siguiente hasta que la anterior esté completa y probada.

---

## Fase 1 — Decision Engine: LLM con 0 autoridad

**Archivos:** `sentinel/core/decision_engine.py`, `sentinel/core/llm_decision_advisor.py`

**Qué hacer:**
1. En `DecisionEngine.evaluate()`, separar el `final_risk_score` en dos: `objective_score` (solo ObjectiveRiskAssessor) y `llm_advisory_score` (solo para informe)
2. La decisión final (`APPROVE/REJECT/REQUIRE_CONFIRM`) usa SOLO `objective_score`
3. El `llm_advisory_score` se guarda en `context_factors` como metadato, no modifica la decisión
4. `DecisionResult` incluye ambos scores para auditoría

**Verificación:** Los tests existentes en `tests/test_decision_engine_seguro.py` siguen pasando

---

## Fase 2 — PresentationLayer en el pipeline

**Archivos:** `sentinel/core/orchestrator.py`, `sentinel/presentation.py`

**Qué hacer:**
1. Inyectar `PresentationLayer` en Orchestrator (opcional, default: None)
2. En `_attach_advisory()`, si hay PresentationLayer, llamar `present(result, mode)` antes de devolver
3. El `ExecutionResult` incluye campo `presentation: Optional[Dict]`
4. `sentinel_bridge.py` usa el presentation del resultado en lugar de llamar directamente

**Verificación:** `tests/test_presentation.py` sigue pasando; la API devuelve datos presentados

---

## Fase 3 — execute_direct sin bypass

**Archivos:** `sentinel/core/orchestrator.py`

**Qué hacer:**
1. `execute_direct()` añade: deep context collection (si hay DeepContextEngine), grounding attachment
2. Si hay GroundingEngine, verificar grounding antes de ejecutar
3. Si hay AdvisoryService, adjuntar advisory al resultado
4. No duplicar lógica — extraer métodos reutilizables de `_process_impl()`

**Verificación:** Los tests de ejecución directa siguen pasando; el pipeline ya no omite etapas

---

## Fase 4 — Grounding preventivo en ToolGateway

**Archivos:** `sentinel/core/tool_gateway.py`, `sentinel/core/orchestrator.py`

**Qué hacer:**
1. `ToolGateway.execute()` acepta parámetro opcional `grounding_requirements`
2. Antes de ejecutar, verifica que los requerimientos de grounding se cumplen
3. Si un requerimiento es `required` y no hay tool que lo satisfaga, rechaza con error
4. En `_process_impl()`, pasar `intent.grounding_requirements` al gateway

**Verificación:** grounding se verifica ANTES de ejecutar cualquier tool

---

## Fase 5 — ApplicationKnowledge en Planner

**Archivos:** `sentinel/core/planner.py`, `sentinel/core/orchestrator.py`

**Qué hacer:**
1. `Planner.plan()` acepta `app_profiles` opcional
2. Si hay perfiles, el planner los usa para:
   - No sugerir acciones para apps no instaladas
   - Preferir herramientas verificadas sobre LLM
3. En `_process_impl()`, si hay deep_context con `installed_apps`, pasarlo al planner

**Verificación:** El planner produce planes más precisos cuando conoce las apps instaladas

---

## Fase 6 — EnvironmentalLearning activo

**Archivos:** `sentinel/core/environment_learning.py`, `sentinel/core/orchestrator.py`

**Qué hacer:**
1. Los cambios detectados (`environment_changes`) afectan el context de decisión:
   - App eliminada → las tools relacionadas tienen mayor riesgo
   - Hardware cambiado → el ModelRouter se re-evalúa
2. El `DecisionEngine` recibe `environment_modifier` desde el contexto
3. El usuario puede ver los cambios en el resultado

**Verificación:** Un cambio en apps/hardware afecta el risk score de acciones relacionadas

---

## Fase 7 — Tests E2E del pipeline completo

**Archivos:** `sidecar/tests/`, `tests/`

**Qué hacer:**
1. Test: pipeline completo con todas las etapas
2. Test: `execute_direct()` ya no omite grounding/advisory
3. Test: DecisionEngine con LLM advisor = 0 influencia en decisión
4. Test: Grounding preventivo en ToolGateway rechaza sin tool
5. Test: PresentationLayer filtra datos técnicos en modo USER

**Verificación:** `python -m pytest tests/ sidecar/tests/` — todos pasan

---

## Fase 8 — Pipeline visible en UI

**Archivos:** `src/components/`

**Qué hacer:**
1. Componente `PipelineStatus` que muestra la etapa actual del pipeline
2. Integrar en `Workbench.tsx` como barra superior
3. Mostrar: etapa activa, resultado de cada etapa, errores
4. Solo visible en modo DEVELOPER (inicialmente)

**Verificación:** La UI muestra el pipeline en tiempo real durante la ejecución

---

## Fase 9 — Reliable Memory con confianza

**Archivos:** `sentinel/core/memory.py`, `sentinel/core/operational_memory.py`

**Qué hacer:**
1. Añadir `confidence: float` a los ítems de memoria
2. Los ítems recuperados incluyen `source` y `confidence`
3. La UI de Memory muestra la confianza de cada ítem
4. El sistema puede filtrar por umbral de confianza

**Verificación:** La memoria distingue ítems de alta vs baja confianza

---

## Fase 10 — Modo USER/DEVELOPER en frontend

**Archivos:** `src/`

**Qué hacer:**
1. Toggle en Settings para cambiar modo
2. Modo USER: oculta scores, tool_ids, detalles técnicos
3. Modo DEVELOPER: muestra todo + pipeline visual
4. El backend recibe el modo y aplica PresentationLayer

**Verificación:** Un usuario normal nunca ve risk scores ni tool_ids
