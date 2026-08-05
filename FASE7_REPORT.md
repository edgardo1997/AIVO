# FASE 7 — VALIDACIÓN DE GUI REAL

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `9bdfe7e`
Versión: `0.1.0-alpha.1`
Canal: `internal-alpha`
Build ID: `internal-alpha-20260804-9bdfe7e`
Entorno: Windows 11 x64, Python 3.12.10, Node v24.18.0, Rust 1.96.1

---

## 1. Estado inicial

Se construyó un instalador `internal-alpha` con el pipeline canónico:

```text
.\scripts\build-alpha.ps1 -Channel internal-alpha -SkipTests
```

Resultado del build:

```text
Sidecar SHA-256: 84DE8827212BCD6C4A763EC878DB8623C67BF08ECF22FB96A1CEE0F0B0594487
Health OK: {"status":"healthy","version":"0.1.0-alpha.1",...}
Bundled sidecar hash matches canonical.
BUILD SUCCESS: internal-alpha-20260804-9bdfe7e
```

---

## 2. Configuración de pantalla

No se evaluaron múltiples resoluciones ni escalados porque la validación se ejecutó de forma automatizada sin observador visual.

---

## 3. Primer inicio

Se creó `scripts/gui-smoke-test.ps1` para:

- instalar el bundle NSIS en un directorio temporal;
- iniciar `sentinel.exe`;
- esperar que el sidecar responda en `127.0.0.1:8765/api/health`;
- capturar logs;
- cerrar la aplicación.

Resultado:

```text
Sentinel PID: 19272
Sidecar PIDs: 24564
Health OK: {"status":"healthy","version":"0.1.0-alpha.1","runtime":"ready","database":"connected","gateway":"212 tools","router":"initialized",...}
```

La aplicación inicia correctamente, arranca el sidecar empaquetado y responde saludable.

---

## 4. Onboarding

No validado visualmente.

La prueba automatizada no puede interactuar con la interfaz WebView.

---

## 5. Chat

No validado visualmente.

Se verificó únicamente que el backend del sidecar está listo para recibir conversaciones.

---

## 6. Historial

No validado.

---

## 7. Settings

No validado.

---

## 8. Permisos

No validado.

---

## 9. Clarificación

No validado.

---

## 10. Consentimiento

No validado.

---

## 11. Auditoría

No validado.

---

## 12. Errores

Se observó un primer intento en el que el sidecar no respondió antes de 30 s. Al aumentar el timeout a 90 s, la aplicación arrancó correctamente. Esto sugiere que el sidecar puede necesitar más tiempo del esperado en el primer inicio, lo que podría requerir un indicador de carga más claro en la GUI.

---

## 13. Loading states

No validados visualmente.

El sidecar tarda entre 10 y 30 s en estar saludable. La GUI podría mostrar un estado de "Conectando con el motor local" durante ese intervalo.

---

## 14. Offline

No validado.

---

## 15. Cloud Authority

No validado.

---

## 16. Idioma

No validado.

---

## 17. Teclado y foco

No validado.

---

## 18. Scroll y modales

No validado.

---

## 19. DPI y ventanas

No validado.

---

## 20. Accesibilidad

No validada.

---

## 21. Demo PDF

No ejecutada desde GUI.

---

## 22. Congelamientos

No observados en el smoke automatizado. El sidecar respondió y el proceso se cerró correctamente.

---

## 23. Recuperación

No validada.

---

## 24. Prueba con usuario normal

No realizada.

---

## 25. Hallazgos P0-P4

| ID | Categoría | Severidad | Descripción |
| -- | --------- | --------- | ----------- |
| GUI-001 | STARTUP | P2 | El sidecar puede tardar más de 30 s en iniciar. El smoke necesitó 90 s de timeout. |

No se detectaron hallazgos visuales por falta de observador.

---

## 26. Correcciones aplicadas

- `scripts/gui-smoke-test.ps1` creado para validación automatizada de arranque.
- Timeout de espera de health aumentado de 30 a 90 s.

---

## 27. Pruebas de regresión

- `npm test` frontend: **151 passed** (previamente)
- `cargo test`: **5 passed** (previamente)
- GUI smoke: **PASSED** (arranque + sidecar health)

---

## 28. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| GUI compilada fue utilizada manualmente | **RECHAZADO** (automatizado, no observador humano) |
| Onboarding se completa sin ayuda | **NO VALIDADO** |
| Chat funciona | **NO VALIDADO** visualmente |
| Streaming funciona | **NO VALIDADO** |
| Cancelación funciona | **NO VALIDADO** |
| Historial persiste | **NO VALIDADO** |
| Settings persisten | **NO VALIDADO** |
| Permisos son comprensibles | **NO VALIDADO** |
| Clarificación funciona visualmente | **NO VALIDADO** |
| Consentimiento evita doble ejecución | **NO VALIDADO** |
| Auditoría es visible y comprensible | **NO VALIDADO** |
| Demo PDF funciona desde GUI | **NO VALIDADO** |
| Errores tienen acciones útiles | **NO VALIDADO** |
| No aparecen stack traces | **NO VALIDADO** |
| No aparecen errores HTTP crudos | **NO VALIDADO** |
| No aparecen rutas internas al usuario | **NO VALIDADO** |
| Modo offline funciona | **NO VALIDADO** |
| Cloud no autorizado no se usa | **NO VALIDADO** |
| Idioma persiste | **NO VALIDADO** |
| Teclado completa flujos esenciales | **NO VALIDADO** |
| Foco es visible y lógico | **NO VALIDADO** |
| Scroll funciona | **NO VALIDADO** |
| DPI y escalado no rompen layouts | **NO VALIDADO** |
| Modales son accesibles | **NO VALIDADO** |
| GUI no se congela | **PARCIAL** (smoke de arranque pasó) |
| Recuperación funciona | **NO VALIDADO** |
| Una persona no técnica completa la tarea principal | **NO VALIDADO** |

---

## 29. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | FASE 7 requiere observación humana y uso manual. No se puede completar con herramientas automatizadas. |
| B-002 | No se cuenta con un usuario externo para prueba de usabilidad. |
| B-003 | El sidecar puede tardar más de 30 s en iniciar; se necesita indicador de carga. |

---

## 30. Veredicto

**RECHAZADO — GUI no validada como producto usable.**

Se logró:

- Construir el instalador `internal-alpha` desde el pipeline canónico.
- Verificar que `sentinel.exe` arranca y el sidecar empaquetado responde a `/api/health`.
- Crear `scripts/gui-smoke-test.ps1` para pruebas de arranque automatizadas.

No se logró:

- Interactuar con la interfaz WebView.
- Validar onboarding, chat, settings, permisos, clarificación, consentimiento, auditoría, demo PDF, idioma, teclado, foco, scroll, DPI, modales, accesibilidad, offline, cloud authority, errores ni recuperación.
- Realizar prueba con un usuario no técnico.

Recomendación: realizar la FASE 7 con un QA humano o con herramientas de accesibilidad/visual específicas que permitan operar la aplicación Tauri y capturar la experiencia real.
