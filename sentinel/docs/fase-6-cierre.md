# Fase 6: Refactor Frontend - Cierre

## Objetivo
Conectar el frontend con el nuevo Orchestrator. El Chat/IntentInput pasa a ser la interfaz primaria de intencion, y se crea un tab Sentinel que muestra el flujo completo: intent -> plan -> decision -> resultado.

## Archivos creados

### sidecar/modules/sentinel_bridge.py (REST bridge)
- Inicializa Orchestrator completo con ToolGateway, PolicyEngine, ContextEngine, IntentEngine, ModelRouter, Planner, DecisionEngine
- POST /api/sentinel/process: recibe utterance, retorna intent + plan + decision + tool_result
- GET /api/sentinel/capabilities: introspeccion de herramientas, intents y modelos
- Integrado con servicios existentes: permissions_svc (nivel), ai_svc (API keys), EMERGENCY_STOP

### sidecar/main.py (editado)
- Importado y montado sentinel_bridge en /api/sentinel

### src/components/Sentinel/
- IntentInput.tsx: input de texto + boton "Go" con estado disabled
- PlanDisplay.tsx: visualiza intent, pasos del plan (con numeracion y badges de impacto), decision, resultado
- Sentinel.tsx: tab completo con ejemplos rapidos, input, resultado e historial

### src/api.ts (editado)
- Nuevo endpoint pi.sentinel.process(utterance)
- Nuevo endpoint pi.sentinel.capabilities()

### src/types.ts (editado)
- Nuevos tipos: SentinelResponse, SentinelPlanStep
- TabType ampliado con "sentinel"

### src/App.tsx (editado)
- Importado Sentinel component
- Agregado case "sentinel" en renderTab

### src/components/Sidebar/Sidebar.tsx (editado)
- Agregado tab "Sentinel" (icono ◆)

### src/index.css (editado)
- Nuevas clases: .intent-input-area, .sentinel-result, .plan-steps, .plan-step, .plan-step-num

## Prueba de aceptacion superada
- tsc -b --noEmit: 0 errores
- oxlint: 0 warnings, 0 errors
- pytest: 43 pass (same baseline, no regressions)
- Bridge inicializa correctamente con Orchestrator

## No se modifico
- Los 10 tabs existentes se mantienen funcionales
- sidecar/ solo se agrego 1 archivo nuevo + 2 lineas en main.py
- src-tauri/ intacto
- Ningun runtime

## Proxima fase
Fase 7: CI/CD + Tests + Blindaje de calidad
- GitHub Actions: lint + test + build en cada push
- Frontend tests con Vitest + Testing Library
- Fix proactive tests en Windows
- CORS restrictivo para produccion
- Logging a archivo con rotacion
