# FASE 9 — VALIDACIÓN DE FLUJOS PRINCIPALES

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `5c03e8b`
Versión: `0.1.0-alpha.1`
Canal: `internal-alpha`
Build ID: `internal-alpha-20260804-9bdfe7e`
Entorno: Windows 11 x64, Python 3.12.10, Node v24.18.0, Rust 1.96.1

---

## 1. Estado inicial

Último build canónico exitoso:

```text
BUILD SUCCESS: internal-alpha-20260804-9bdfe7e
Sidecar SHA-256: 84DE8827212BCD6C4A763EC878DB8623C67BF08ECF22FB96A1CEE0F0B0594487
```

Precondiciones:

- Working tree limpio.
- Build ID visible en `artifacts/internal-alpha/manifest.json`.
- Sidecar canónico empaquetado y verificado.
- No se requiere intervención manual.

---

## 2. Datos de prueba

Se creó `scripts/e2e-prep.ps1` para generar un entorno controlado:

```text
C:\Users\edgar\AppData\Local\Temp\SentinelE2E
├── Downloads
│   ├── invoice_old.pdf
│   ├── report_middle.pdf
│   └── report_latest.pdf
├── Documents
├── Reviewed
└── manifest.json
```

`report_latest.pdf` es el más reciente por `mtime`, con los headers mínimos de PDF.

---

## 3. Flujo A — Primer inicio

**Estado: NO VALIDADO en GUI real.**

Se ejecutó el smoke de arranque (`scripts/gui-smoke-test.ps1`):

```text
Sentinel PID: 19272
Sidecar PIDs: 24564
Health OK: {"status":"healthy",...}
```

Esto prueba que el instalador y la aplicación inician, pero no el onboarding ni el chat interactivo.

---

## 4. Flujo B — Conversación

**Estado: NO VALIDADO en GUI real.**

Se verificó que el sidecar expone `POST /api/v1/execute` y `/api/v1/chat`, pero no se realizó conversación desde la WebView.

---

## 5. Flujo C — Ambigüedad

**Estado: NO VALIDADO en GUI real.**

Se verificó que `Clarification` y `ConsentDialog` renderizan en tests unitarios. No se probó el recorrido end-to-end con interacción real.

---

## 6. Flujo D — Demo PDF

**Estado: NO VALIDADO en GUI real.**

Se preparó el entorno con PDFs de prueba. No se ejecutó la demo desde la interfaz Tauri. El flujo de backend podría validarse vía API de sidecar, pero eso no equivale a validar la GUI.

---

## 7. Flujo E — Cloud Authority

**Estado: NO VALIDADO en GUI real.**

El backend tiene `CloudAuthority` y defaults `local_only`, pero no se probó el rechazo/aprobación de cloud desde la interfaz.

---

## 8. Flujo F — Settings y persistencia

**Estado: NO VALIDADO en GUI real.**

`AppContext` persiste el modo `user`/`developer` en `localStorage`. No se validó el flujo completo de cambiar idioma, carpetas y cloud, cerrar y reabrir.

---

## 9. Auditoría transversal

**Estado: NO VALIDADO en GUI real.**

Los componentes `Audit` y `ConsentDialog` muestran estados y detalles técnicos plegados. No se validó coherencia con acciones reales.

---

## 10. Persistencia transversal

**Estado: PARCIAL.**

- Conversaciones: persisten en `localStorage` según `Workbench`.
- Modo usuario/desarrollador: persiste en `localStorage` según `AppContext`.
- Settings del sidecar: persisten en SQLite; no se validó cierre y reapertura.

---

## 11. Intervención manual detectada

Ninguna. Esta fase no se completó.

---

## 12. Repeticiones

Ninguna. Esta fase no se completó.

---

## 13. Automatización E2E

Se preparó `scripts/e2e-prep.ps1` para crear datos de prueba. No se automatizó Playwright ni WebDriver por falta de GUI validation previa.

---

## 14. Hallazgos P0-P4

Ningún hallazgo nuevo.

---

## 15. Correcciones aplicadas

Ninguna en esta fase.

---

## 16. Pruebas de regresión

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed** |
| `cargo test --locked` | **5 passed** |
| `gui-smoke-test.ps1` | **PASSED** |

---

## 17. Archivos modificados

- `scripts/e2e-prep.ps1` (nuevo)
- `FASE9_REPORT.md` (nuevo)

---

## 18. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Flujo A funciona desde GUI compilada | **NO VALIDADO** |
| Flujo B funciona desde GUI compilada | **NO VALIDADO** |
| Flujo C funciona desde GUI compilada | **NO VALIDADO** |
| Flujo D funciona desde GUI compilada | **NO VALIDADO** |
| Flujo E funciona desde GUI compilada | **NO VALIDADO** |
| Flujo F funciona desde GUI compilada | **NO VALIDADO** |
| No se usaron comandos manuales | **N/A** |
| Onboarding persiste | **NO VALIDADO** |
| Conversaciones persisten | **PARCIAL** |
| Settings persisten | **PARCIAL** |
| Permisos persisten | **NO VALIDADO** |
| Cloud Authority persiste | **NO VALIDADO** |
| Grants no se reutilizan | **NO VALIDADO** |
| Auditoría es coherente | **NO VALIDADO** |
| Errores comprensibles | **NO VALIDADO** |
| Estados parciales representados correctamente | **NO VALIDADO** |
| Cada flujo repetido 3 veces | **NO VALIDADO** |
| Pruebas de regresión para bugs | **N/A** |
| P0 abiertos | **N/A** |
| P1 abiertos en flujos | **N/A** |

---

## 19. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | FASE 7 no validó GUI real; FASE 9 requiere interacción humana que no se puede realizar de forma automatizada. |
| B-002 | No hay usuario no técnico disponible para prueba de flujos. |
| B-003 | No hay herramienta de automatización E2E para Tauri configurada. |

---

## 20. Cambios pospuestos para Beta

- Automatización E2E completa con Playwright/WebDriver.
- Pruebas de flujo con múltiples usuarios.
- Validación de persistencia en perfiles Windows distintos.

---

## 21. Veredicto

**RECHAZADO — no se validaron los seis flujos principales desde la GUI compilada.**

Se logró:

- Preparar un entorno de prueba limpio con datos controlados.
- Confirmar que `npm test`, `cargo test` y el smoke de arranque pasan.
- Documentar el plan de validación para cada flujo.

No se logró:

- Ejecutar e interactuar con la GUI compilada para los flujos A-F.
- Validar persistencia transversal por reabrir/cerrar.
- Validar auditoría de acciones reales.
- Repetir flujos ni clasificar hallazgos.

Recomendación: completar FASE 9 con un QA humano que use el instalador `internal-alpha` y el entorno preparado por `scripts/e2e-prep.ps1`.
