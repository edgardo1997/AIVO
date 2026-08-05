# FASE 8 — SIMPLIFICACIÓN DE EXPERIENCIA PARA USUARIOS NORMALES

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `78f7a71`
Versión: `0.1.0-alpha.1`
Build ID: `internal-alpha-20260804-9bdfe7e`

---

## 1. Estado inicial

Sentinel ya contaba con:

- `AppContext` con modo `user`/`developer` y persistencia (`sentinel.ui.mode`).
- Navegación `WorkbenchSidebar` que mostraba todas las vistas.
- `ConsentDialog` con detalles técnicos plegados.
- Tests frontend (151 passed).

---

## 2. Inventario de pantallas

| Vista | Usuario normal la necesita | Desarrollador la necesita | Acción |
| ----- | -------------------------- | ------------------------- | ------ |
| Chat | Sí | Sí | Mantener como pantalla principal |
| Panel | Sí | Sí | Mantener |
| Permisos | Sí | Sí | Mantener |
| Auditoría | Sí | Sí | Mantener |
| Ayuda | Sí | Sí | Mantener |
| Centro de modelos | No | Sí | Ocultar en modo usuario |
| Consola/Ejecutor | No | Sí | Ocultar en modo usuario |
| Observabilidad | No | Sí | Ocultar en modo usuario |
| Flota | No | Sí | Ocultar en modo usuario |
| Agentes/Plugins/Triggers | No | Sí | Ocultar en modo usuario |
| Políticas | No | Sí | Ocultar en modo usuario |
| Vault | Sí (indirecto) | Sí | Mantener bajo Permisos |
| Archivos/Conocimiento/Memoria | Parcial | Sí | Ocultar en modo usuario Alpha |

---

## 3. Modo usuario

Se modificó `WorkbenchSidebar` para mostrar únicamente las vistas permitidas en modo usuario:

```text
dashboard, sentinel, permissions, audit, help
```

```tsx
const userVisibleViews: Set<ViewKey> = new Set([
  "dashboard",
  "sentinel",
  "permissions",
  "audit",
  "help",
]);
```

En modo `developer` se muestran todas las vistas.

---

## 4. Modo desarrollador

Mantienen las mismas autorizaciones. La activación requiere acción consciente:

- **Configuración > Interfaz**
- Atajo `Ctrl+Shift+D`

El modo es pura presentación; no otorga autoridad adicional.

---

## 5. Contrato entre modos

- Misma configuración.
- Mismos permisos.
- Mismos datos.
- Misma auditoría.
- Cambio de modo sin reiniciar sidecar ni perder conversación.

---

## 6. Onboarding

Se mantuvo el onboarding existente. No se añadieron configuraciones avanzadas. Pendiente: reducir a cuatro decisiones esenciales.

---

## 7. Defaults seguros

El contexto `AppContext` inicia en modo `user`. Cloud no autorizado por defecto. IA local preferida. Developer mode desactivado.

---

## 8. Chat

El chat continúa como pantalla principal. No se modifica la estructura.

---

## 9. Estado local/cloud

El componente `ConnectionStatus` y la barra de estado muestran conexión. Pendiente: simplificar mensajes a tres estados: IA local, IA cloud, sin modelo.

---

## 10. Permisos

Se mantienen en `permissions`. `ConsentDialog` mejorado.

---

## 11. Actividad

`LiveActivity` y `LiveActivityStage` muestran progreso simple. Sin cambios en esta fase.

---

## 12. Auditoría

`Audit.tsx` mantiene vista. Pendiente: separar en simple/técnica con `<details>`.

---

## 13. Settings

Se añadió sección **Interfaz** en `Settings`:

- Explica modo usuario y modo desarrollador.
- Toggle para cambiar de modo.
- Atajo documentado.

---

## 14. Jerga técnica

Se documenta en `docs/UX_DESIGN.md` y se aplican etiquetas humanas en `ConsentDialog`:

| Técnico | Usuario |
| ------- | ------- |
| filesystem.copy | Copiar archivo |
| filesystem.move | Mover archivo |
| filesystem.read | Leer archivo |
| filesystem.list | Listar archivos |
| filesystem.create_dir | Crear carpeta |
| search.find | Buscar archivos |

---

## 15. Errores

`ErrorBox` y `ErrorRecoveryPanel` estructuran mensajes comprensibles. Pendiente: auditar todos los textos para eliminar JSON/HTTP/stack traces.

---

## 16. Navegación

Modo usuario:

```text
Nuevo chat
Conversaciones
Panel
Permisos
Auditoría
Ayuda
```

Modo desarrollador:

```text
(por secciones en WorkbenchSidebar)
Producto, Sistema, Datos, Administración, Seguridad
```

---

## 17. Accesibilidad

- `ConsentDialog` captura foco y usa `aria-modal`.
- `WorkbenchSidebar` navegable con teclado.
- Pendiente: foco en cambio de modo, lector de pantalla, contraste.

---

## 18. Pruebas de comprensión

No realizadas con usuarios reales.

---

## 19. Prueba con usuario normal

No realizada.

---

## 20. Archivos modificados

- `src/components/Workbench/WorkbenchSidebar.tsx`
- `src/components/Settings/Settings.tsx`
- `src/components/ConsentDialog/ConsentDialog.tsx`
- `docs/UX_DESIGN.md` (nuevo)
- `FASE8_REPORT.md` (nuevo)

---

## 21. Pruebas ejecutadas

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed** |
| `npm run build` | **exit 0** |

---

## 22. Cambios pospuestos para Beta

- Rediseño visual completo.
- Animaciones decorativas.
- Nuevos paneles (Observability avanzado, Product views).
- Onboarding de más de cuatro pasos.
- Métricas y costos visibles por defecto.
- Preferencias no esenciales.

---

## 23. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Modo usuario está definido | **COMPLETADO** |
| Modo desarrollador está definido | **COMPLETADO** |
| Modo usuario es el predeterminado | **COMPLETADO** |
| Ambos modos comparten lógica y autoridad | **COMPLETADO** |
| Onboarding tiene máximo cuatro decisiones esenciales | **PARCIAL** (pendiente reducción de opciones) |
| Cloud está desautorizado por defecto | **COMPLETADO** |
| Permisos usan lenguaje humano | **PARCIAL** (mejorado en ConsentDialog, falta revisión completa) |
| Chat es la pantalla principal | **COMPLETADO** |
| Actividad muestra progreso simple | **COMPLETADO** |
| Auditoría tiene vista simple y técnica | **PARCIAL** |
| Settings básicos están separados de avanzados | **COMPLETADO** |
| Jerga técnica está oculta en modo usuario | **PARCIAL** |
| Errores son comprensibles y accionables | **PARCIAL** |
| IDs y JSON no aparecen en modo usuario | **PARCIAL** |
| Developer mode no otorga autoridad adicional | **COMPLETADO** |
| Navegación por teclado funciona | **PARCIAL** |
| La GUI compilada fue validada | **RECHAZADO** (FASE 7) |
| Una persona no técnica completa la tarea principal | **NO VALIDADO** |
| No se agregaron funciones nuevas | **COMPLETADO** |

---

## 24. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | FASE 7 no pudo validar la GUI visual; bloquea el criterio de tarea con usuario normal. |
| B-002 | Onboarding aún puede presentar demasiadas opciones. |
| B-003 | Auditoría simple/técnica no separada explícitamente. |
| B-004 | Falta prueba de comprensión con usuarios no técnicos. |

---

## 25. Veredicto

**PARCIAL — simplificación implementada en navegación, consentimiento y settings, pero sin validación humana.**

Se logró:

- definir y aplicar modo usuario/desarrollador;
- filtrar navegación según modo;
- agregar toggle en Settings con persistencia;
- mejorar etiquetas de acciones en `ConsentDialog`;
- documentar la estrategia en `docs/UX_DESIGN.md`;
- pasar `npm test` y `npm run build`.

Pendiente:

- reducir onboarding a cuatro pasos;
- separar auditoría simple/técnica;
- auditar todos los mensajes de error;
- completar FASE 7 con un usuario real.
