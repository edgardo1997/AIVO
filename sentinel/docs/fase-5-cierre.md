# Fase 5: Planner + Decision Engine - Cierre

## Objetivo
El sistema puede descomponer una intencion en pasos multi-herramienta (Planner) y evaluar si debe ejecutarlos segun riesgo y nivel de permiso (DecisionEngine).

## Archivos creados

### sentinel/core/planner.py
- PlanStep: un paso individual (tool_id, params, desc, is_reversible, rollback, estimated_impact, depends_on)
- Plan: coleccion de pasos + risk_score + descripcion
- Planner:
  - 12 definiciones de pasos (1 paso para queries simples, 2+ pasos para analisis complejos)
  - plan(intent): genera Plan con pasos, dependencias y calculo de riesgo
  - _calculate_risk(): combina impacto de pasos (max) + riesgo de accion (query<analyze<configure<control<execute)
  - describe_plan(): representacion legible para mostrar al usuario

### sentinel/core/decision_engine.py
- Decision: enum APPROVE, REJECT, REQUIRE_CONFIRM, MODIFY
- DecisionResult: decision + plan + reason + modifications
- DecisionEngine:
  - Thresholds por nivel de permiso (view/confirm/auto/admin)
  - Logica: risk <= auto → APPROVE, risk <= confirm → REQUIRE_CONFIRM, else REJECT
  - Considera pasos irreversibles de alto impacto como factor agravante
  - should_skip_decision(): queries simples pasan directo sin evaluacion

### sentinel/core/orchestrator.py (refactorizado)
- ExecutionPlan ahora incluye plan (Planner) y 	ask_type
- ExecutionResult ahora incluye decision (DecisionResult)
- Orchestrator.process(): intent → plan → decision → (approve? execute : return early)
- Flujo completo con 3 puntos de salida:
  1. REJECT: retorna error sin ejecutar
  2. REQUIRE_CONFIRM: retorna plan para que el usuario confirme
  3. APPROVE: ejecuta y retorna resultado

## Prueba de aceptacion superada
- Planner: 1 paso (CPU), 2 pasos secuenciales (Health), parametros extraidos (limit=10), describe() funciona
- DecisionEngine: query+confirm=approve, query+admin=approve, execute+view=reject, execute+confirm=require_confirm
- Orchestrator: query salta decision, analyze pasa por decision y se auto-aprueba
- 8/8 subtests pasan

## No se modifico
- sidecar/ intacto, src/ intacto, src-tauri/ intacto

## Proxima fase
Fase 6: Refactor frontend
- Chat.tsx pasa a ser interfaz primaria de intencion
- Dashboard.tsx pasa a ser panel de explicabilidad (planes, decisiones, resultados)
- Nuevo componente: IntentInput (texto + boton + status)
- Nuevo componente: PlanDisplay (visualiza pasos, riesgo, confirmacion)
- Eliminar tabs individuales redundantes
- Conectar Orchestrator via api.ts (POST /api/sentinel/process)
