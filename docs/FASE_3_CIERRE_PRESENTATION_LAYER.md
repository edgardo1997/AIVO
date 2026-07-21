# Fase 3 — Cierre: Presentation Layer

## Resultado

Sentinel presenta ahora el estado del pipeline en dos niveles coherentes. La vista normal explica qué ocurrió, el riesgo, la evidencia y el siguiente paso. La vista técnica muestra intención, decisión y herramientas únicamente cuando el usuario la solicita.

La capa de presentación no decide, autoriza ni ejecuta. Solo traduce el resultado confiable producido por el Orchestrator.

## Contrato de presentación

Cada resultado gobernado puede incluir:

- `status`: completado, pendiente de aprobación, vista previa, fallo o no ejecutado.
- `title` y `summary`: explicación orientada al usuario.
- `risk`: nivel comprensible y puntuación solo en modo técnico.
- `evidence`: requisitos, fuentes verificadas y estado de cumplimiento.
- `next_action`: instrucción concreta cuando se necesita intervención.
- `details`: intención, decisión y herramientas solo en modo desarrollador.

El contrato tiene versión propia para permitir evolución sin romper integraciones.

## Seguridad y privacidad

- La presentación nunca cambia un rechazo, bloqueo o fallo por éxito.
- Una acción pendiente afirma explícitamente que todavía no fue ejecutada.
- La vista normal no muestra rutas internas, errores crudos ni puntuaciones numéricas.
- La vista técnica tampoco duplica los datos completos devueltos por herramientas.
- Los campos API anteriores se conservan temporalmente para compatibilidad.

## Interfaz

- El Centro de acciones muestra primero la conclusión, evidencia y próximo paso.
- Intención, plan, resultados y rollback están dentro de detalles progresivos.
- Simulación e ID de sesión aparecen solo en vista técnica.
- El chat muestra una señal compacta de fuentes verificadas y riesgo.
- Los controles principales y ejemplos quedaron unificados en español.
- El resumen principal usa una región accesible para anunciar cambios de estado.

## Validación

- Backend: 1820 pruebas aprobadas, 1 omitida y 23 excluidas por marcadores.
- Frontend: 126 pruebas aprobadas en 28 archivos.
- Ruff y oxlint: limpios.
- TypeScript y Vite: build correcto.
- Tauri/Rust: `cargo check` correcto.
- Permanecen dos advertencias externas de deprecación en Starlette/httpx y ReportLab.

## Siguiente fase

Fase 4: Reliable Memory. La memoria debe incorporar procedencia, confianza, alcance por usuario y reglas de recuperación/borrado sin crear una segunda base de datos ni duplicar el historial existente.
