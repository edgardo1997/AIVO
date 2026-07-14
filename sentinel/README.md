# Directorio sentinel/

Nueva arquitectura del proyecto. En construccion.

## Estructura

sentinel/
  core/           Motores centrales (Intent, Decision, Policy, Planner, Context, Memory, Model Router, Tool Gateway)
  adapters/       Adaptadores a sistemas externos (OS, archivos, red, apps, etc.)
  docs/           Documentacion tecnica y de identidad del proyecto

## Reglas

- Todo codigo nuevo se escribe aqui, no en sidecar/
- sidecar/ se mantiene intacto como runtime legacy
- Cada fase produce un documento de cierre en docs/
- No mezclar fases. No abrir refactors gigantes.

## Progreso

- [x] Fase 0: Preparacion
- [ ] Fase 1: Tool Gateway + Adapter Interface
- [ ] Fase 2: Policy Engine
- [ ] Fase 3: Context Engine + Memory
- [ ] Fase 4: Intent Engine + Model Router
- [ ] Fase 5: Planner + Decision Engine
- [ ] Fase 6: Refactor frontend
- [ ] Fase 7: CI/CD + Tests + Blindaje
