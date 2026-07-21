# Fase 1 — Cierre del Decision Engine seguro

**Fecha:** 18 de julio de 2026  
**Alcance:** separación estricta entre consejo de IA y autoridad del sistema

## Objetivo

Garantizar que ningún modelo de IA pueda aprobar, rechazar, ejecutar ni modificar
el riesgo de una acción. La autoridad permanece en datos objetivos, simulación,
permisos, políticas y autorización humana.

## Contrato resultante

1. `ObjectiveRiskAssessor` calcula riesgo, confirmación y rechazo.
2. `DecisionEngine.evaluate()` produce una decisión exclusivamente objetiva.
3. `DecisionEngine.evaluate_async()` conserva esa decisión y recoge advisory
   opcional fuera de banda.
4. `LLMOutputValidator` valida el objeto real del advisory antes de registrarlo.
5. El advisory nunca se copia a puntajes, permisos ni decisiones.
6. `ToolGateway` conserva la última autoridad sobre políticas y ejecución.

## Correcciones realizadas

- Eliminado el prompt muerto que pedía al modelo modificar el riesgo.
- Eliminado `asyncio.run()` del flujo de producción; ya no se intenta crear un
  segundo bucle de eventos dentro del orquestador.
- La llamada síncrona al proveedor se mueve a un hilo de trabajo para no bloquear
  el bucle principal.
- El validador acepta de forma segura tanto diccionarios como `AdvisoryResult`.
- Conectar un router después del arranque actualiza siempre el advisor.
- Se añadió compatibilidad controlada con consumidores y dobles antiguos que aún
  implementan únicamente `evaluate()`.
- Las consultas de bajo riesgo no invocan al advisor remoto.

## Evidencia de separación de autoridad

Las pruebas nuevas verifican que un mismo plan conserva exactamente la misma
decisión y puntaje cuando el modelo responde `low`, `medium`, `high` o
`critical`. También se verifica el mismo resultado con JSON malformado,
confianza fuera de rango y caída del proveedor.

## Puertas de calidad

| Puerta | Resultado |
|---|---|
| Backend completo | 1809 pasan, 1 omitida, 23 deseleccionadas |
| Frontend | 125/125 |
| Ruff | limpio |
| Oxlint | limpio |
| TypeScript/Vite | build limpio |
| Rust/Tauri | `cargo check` limpio |

## Excepciones no bloqueantes

- La prueba proactiva V1 continúa omitida porque ese endpoint no pertenece a
  esta fase y no se agregaron capacidades nuevas.
- Permanecen avisos externos de transición de Starlette/httpx y ReportLab para
  Python 3.14.
- No se realizó commit ni se descartaron cambios previos del usuario.

## Criterio de salida

- [x] El LLM no modifica el riesgo objetivo.
- [x] El LLM no autoriza ni rechaza acciones.
- [x] Advisory inválido o no disponible falla de forma segura.
- [x] No se bloquea el bucle asíncrono del orquestador.
- [x] Regresión completa verde.

La Fase 1 queda cerrada. La siguiente fase del plan vigente es Grounding
integrado.
