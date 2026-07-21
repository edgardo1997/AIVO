# Fase 4 — Cierre de Reliable Memory

## Resultado

Sentinel conserva una sola memoria operacional. No se creó otra base ni una abstracción paralela. La memoria existente ahora aplica un contrato uniforme de propietario, procedencia, confianza, vigencia y borrado.

La memoria sigue siendo contexto consultivo. Nunca concede permisos, reduce riesgo, autoriza herramientas ni sustituye a DecisionEngine, PolicyEngine o ToolGateway.

## Cambios aplicados

- La recuperación de historial se filtra dentro del backend por `user_id + session_id`.
- Las preferencias de sesión nuevas se almacenan con clave compuesta `user_id + session_id + key`.
- Los episodios declaran `source`, `confidence`, `expires_at` y `session_id`.
- Los recuerdos caducados o con metadata temporal inválida no se recuperan.
- Las preferencias aprendidas pueden filtrarse por confianza; el Orchestrator exige 0.6.
- El borrado elimina ejecuciones, episodios y preferencias del propietario y reconstruye patrones con la evidencia restante.
- La API devuelve una señal de confianza explícita y marca la memoria como `advisory_only`.
- SQLite migra a esquema v2 y añade índices para propietario, sesión y tiempo.

## Separación deliberada de datos

El historial visible del chat, la memoria operacional y KnowledgeBase permanecen separados:

- conversaciones: registro que el usuario ve y administra;
- memoria operacional: resultados concisos usados como contexto;
- KnowledgeBase: contenido documental recuperable.

Fusionarlos habría mezclado retención, permisos y niveles de confianza distintos. El Orchestrator es el punto de composición; ninguna de estas fuentes se convierte en autoridad.

## Compatibilidad y migración

- La tabla heredada `user_preferences` permanece disponible para llamadas antiguas.
- Las llamadas con identidad usan `session_preferences`, aislada por propietario.
- La apertura de una base v1 crea las estructuras v2 sin borrar ni reescribir conversaciones o ejecuciones existentes.
- Sentinel rechaza bases con una versión futura que el binario no comprenda.

## Verificación

- 113 pruebas focalizadas de memoria, SQLite y Orchestrator: aprobadas.
- 39 pruebas de migración, bootstrap e integración de memoria: aprobadas tras actualizar el contrato de esquema.
- Ruff sobre todos los archivos modificados: limpio.
- `git diff --check`: limpio; solo se muestran advertencias de normalización LF/CRLF ya presentes en el árbol de trabajo.

La ejecución monolítica de toda la suite fue interrumpida por el límite del canal de terminal y produjo `OSError: [Errno 22]` al cerrarse stdout. No produjo una aserción fallida de Sentinel. La línea base completa anterior a esta fase era 1820 aprobadas, 1 omitida y 23 excluidas; la cobertura directamente afectada por esta fase sí quedó verificada.

## Riesgo residual

La tabla heredada de preferencias carece de propietario porque pertenece al esquema v1. Se conserva solo para compatibilidad. Todo flujo autenticado del Orchestrator usa la tabla v2 aislada. Su eliminación definitiva debe hacerse únicamente cuando exista una política de migración de datos heredados y una versión mayor permita retirar compatibilidad.
