# Fase 2 — Cierre: Grounding integrado

## Resultado

Sentinel ya distingue las consultas que necesitan datos verificables de la máquina y exige que el plan contenga una fuente real antes de ejecutarse. La salida del mismo ToolGateway gobernado se reutiliza como evidencia; no se ejecutan herramientas ocultas ni duplicadas.

## Flujo final

1. IntentEngine interpreta la solicitud.
2. GroundingEngine declara requisitos objetivos, sin ejecutar nada.
3. Planner crea el plan.
4. Orchestrator rechaza planes incapaces de producir la evidencia requerida.
5. Políticas, autorización y ToolGateway gobiernan la única ejecución real.
6. Orchestrator verifica la respuesta y registra herramienta, fecha, frescura y resultado.
7. API y chat exponen la procedencia mediante `grounding_results` y `grounding_satisfied`.

## Garantías

- Una respuesta de un modelo nunca cuenta como evidencia de estado local.
- Las acciones mutables no disparan lecturas preliminares ocultas.
- Una ejecución no queda aprobada si falta grounding obligatorio.
- Los parámetros de caché usan una clave canónica y estable.
- La memoria persiste categorías como texto serializable.
- CPU, memoria, disco, red, procesos, archivos consultados y aplicaciones usan herramientas concretas.

## Validación

- Backend: 1815 pruebas pasaron, 1 omitida y 23 excluidas por marcadores.
- Grounding/orquestación focalizados: 69 pruebas pasaron.
- Ruff sobre archivos modificados: limpio.
- Las dos advertencias externas son de compatibilidad/deprecación en Starlette/httpx y ReportLab.

## Decisión arquitectónica

No se añadió grounding dentro de ToolGateway como una segunda ejecución. ToolGateway conserva su responsabilidad de aplicar políticas y ejecutar; Orchestrator valida que ese resultado satisface la evidencia declarada. Esto evita ciclos, bypass de permisos y consumo duplicado.

## Siguiente fase

Fase 3: Presentation Layer. Debe traducir intención, plan, decisión, riesgo y procedencia a lenguaje útil para el usuario sin ocultar la trazabilidad técnica disponible.
