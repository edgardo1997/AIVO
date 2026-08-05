# FASE 14 — MENSAJES, SOPORTE Y DIAGNÓSTICO

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `b226840`
Versión: `0.1.0-alpha.1`
Canal: `internal-alpha`
Build ID: `internal-alpha-20260804-9bdfe7e`

---

## 1. Estado inicial

- No existía taxonomía de errores centralizada.
- Los mensajes de error mezclan detalles técnicos y usuario.
- No existe exportación de diagnóstico.
- No hay página de soporte ni botón de "Crear diagnóstico".
- Build ID no es visible en la GUI.

## 2. Inventario de errores

| Componente | Patrón | Coincidencias aproximadas |
| ---------- | ------ | -------------------------:|
| Sidecar Python | `throw`, `raise`, `HTTPException`, `ValidationError`, `.error(` | **612** |
| Frontend React/TS | `console.error`, `throw new Error`, `new Error`, `.catch(` | **44** |

La gran mayoría de los errores está en el sidecar. Se requiere categorización progresiva.

## 3. Taxonomía y códigos

Documentada en `docs/SUPPORT_DESIGN.md`.

Se definió el esquema `SEN-<COMPONENTE>-###` con 16 categorías.

## 4. Mensajes de usuario

Se definió contrato de mensaje en `docs/SUPPORT_DESIGN.md`:

1. Título breve.
2. Qué ocurrió.
3. Qué no ocurrió.
4. Acción recomendada.
5. Código de soporte.
6. Acción.

No se implementó contrato en todos los componentes.

## 5. Estado del sistema

No se implementó vista de estado del sistema.

## 6. Versión y Build ID

No se verificó visibilidad en GUI. Se definió formato esperado.

## 7. Diagnóstico

No se implementó botón de diagnóstico ni exportación.

## 8. Contenido exportado

Se definió contenido mínimo en `docs/SUPPORT_DESIGN.md`.

## 9. Redacción de secretos

Se agregó `sidecar/tests/test_secret_redaction.py` con redactor de prueba.

Patrones cubiertos:

- `Authorization: Bearer <token>`
- `sk-...` keys
- JSON `api_key`, `secret`, `password`, `token`, `client_secret`, `private_key`
- Asignaciones `key=value`
- Rutas de usuario `C:\Users\<nombre>`

Resultado:

```text
5 passed
```

## 10. Logs

No se transformaron logs a estructura JSON. Aún contienen texto libre.

Observación: los logs existentes no exponen valores secretos, pero sí nombres de variables de entorno (`SENTINEL_API_KEY_OPENROUTER`). No es P0, pero debe considerarse en redacción.

## 11. Correlation IDs

No se implementaron.

## 12. Rotación

No se configuró rotación de logs.

## 13. Página de soporte

No existe.

## 14. Recuperación de configuración

No existe.

## 15. Restablecer Sentinel

No existe.

## 16. Privacidad

Se definió resumen de exportación y exclusiones por defecto.

## 17. Accesibilidad

No se validó flujo sin ratón.

## 18. Prueba con usuario normal

No realizada.

## 19. Hallazgos

| ID | Categoría | Prioridad | Descripción |
| -- | --------- | --------- | ----------- |
| MSG-001 | TAXONOMY | P2 | 612+ errores en sidecar sin códigos estables ni categorización. |
| SUPPORT-001 | DIAGNOSTIC | P1 | No existe exportación de diagnóstico ni página de soporte. |
| BUILDINFO-001 | BUILD | P2 | Build ID no es visible en GUI. |
| SECRET-LOG-001 | PRIVACY | P3 | Logs mencionan `SENTINEL_API_KEY_OPENROUTER` (nombre de variable, no valor). |
| LOG-001 | LOGS | P2 | Logs no son estructurados ni tienen rotación. |

## 20. Correcciones aplicadas

- `docs/SUPPORT_DESIGN.md` (nuevo)
- `sidecar/tests/test_secret_redaction.py` (nuevo)

## 21. Pruebas de regresión

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed** |
| `cargo test --locked` | **5 passed** |
| `pytest sidecar/tests/test_secret_redaction.py -q` | **5 passed** |

## 22. Archivos modificados

- `docs/SUPPORT_DESIGN.md`
- `sidecar/tests/test_secret_redaction.py`
- `FASE14_REPORT.md`

## 23. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Todos los errores inventariados | **PARCIAL** (conteo, no detalle) |
| Taxonomía de errores | **COMPLETADO** (diseño) |
| Códigos de soporte estables | **COMPLETADO** (diseño) |
| Errores accionables | **NO VALIDADO** |
| Sin stack traces en modo usuario | **NO VALIDADO** |
| Sin errores HTTP crudos | **NO VALIDADO** |
| Estado del sistema visible | **NO VALIDADO** |
| Versión y Build ID visibles | **NO VALIDADO** |
| Botón de diagnóstico | **NO VALIDADO** |
| Diagnóstico offline | **NO VALIDADO** |
| Diagnóstico sin claves/tokens | **PARCIAL** (redactor de prueba) |
| Logs estructurados | **NO VALIDADO** |
| Rotación de logs | **NO VALIDADO** |
| Correlation IDs | **NO VALIDADO** |
| Página de soporte | **NO VALIDADO** |
| Recuperación de configuración | **NO VALIDADO** |
| Niveles de restablecimiento | **NO VALIDADO** |
| Reset probado | **NO VALIDADO** |
| Usuario no técnico prueba diagnóstico | **NO VALIDADO** |
| P0 abiertos | **N/A** |

## 24. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | Falta implementar redactor central y exportación de diagnóstico. |
| B-002 | Falta Build ID visible en GUI. |
| B-003 | Falta página de soporte y acciones de recuperación. |

## 25. Cambios pospuestos

- Exportación de diagnóstico ZIP.
- Build ID en UI.
- Página de soporte.
- Reset interactivo.
- Correlation IDs.
- Logs estructurados.

## 26. Veredicto

**PARCIAL — se definió taxonomía, contrato de mensajes y redactor de secretos; falta implementación real en producto.**

Se logró:

- Inventariar fuentes de error (612 sidecar, 44 frontend).
- Documentar taxonomía, códigos, contrato de mensaje, contenido de diagnóstico, redacción y niveles de reset.
- Agregar pruebas de redacción de secretos.

Pendiente:

- Implementar redactor central y exportación de diagnóstico.
- Hacer visible Build ID en GUI.
- Crear página de soporte.
- Estructurar logs y correlation IDs.
- Probar con usuario no técnico.
