# Plan de Completamiento Técnico — Sentinel

**Fecha:** 2026-08-05  
**Rama técnica recomendada:** `feature/technical-phase-completion` (nueva, a partir de `main`)  
**Rama de referencia UX:** `feature/normal-user-experience` (congelada, no crecerá)  
**Build congelado para validación manual:** `internal-alpha-20260805-229cf37`  

---

## 1. Estado consolidado de fases

| Fase/Bloque | Estado | Bloqueos técnicos | Bloqueos manuales | Dependencias | Próxima acción |
|-------------|--------|-------------------|-------------------|--------------|----------------|
| FASE 0 | COMPLETADO | — | — | — | — |
| FASE 1 | COMPLETADO | — | — | — | — |
| FASE 2 | COMPLETADO | — | — | — | — |
| FASE 3 | COMPLETADO | — | — | — | — |
| FASE 4 | COMPLETADO | — | — | — | — |
| FASE 5 | COMPLETADO | — | — | — | — |
| FASE 6 | COMPLETADO (internal-alpha) | — | — | — | — |
| FASE 10 | COMPLETADO | — | — | — | — |
| FASE 11 | COMPLETADO | — | — | — | — |
| FASE 14 | PARCIAL — build ID embebido; diagnostic backend; logs estructurados con build_id/correlation_id | Ninguno técnico | GUI manual (`docs/validation/FASE14_GUI_MANUAL_CHECKLIST.md`) | BLOQUE F | No bloquear; continuar fases técnicas |
| BLOQUE A | COMPLETADO | — | — | — | — |
| BLOQUE B | COMPLETADO | — | — | — | — |
| BLOQUE C | COMPLETADO | — | — | — | — |
| BLOQUE D | COMPLETADO | — | — | — | — |
| BLOQUE E | COMPLETADO | — | — | — | — |
| BLOQUE F | PARCIAL | Deuda Rust/Tauri logs; frontend logging wrapper; encriptación logs en disco; ProviderManager/ModelRouter consolidados parcial con tests verdes | Validación manual GUI | FASE 14 | Terminar provider/router, luego Rust/frontend |
| BLOQUE G | NO DEFINIDO | Alcance por definir | — | FASE 7, 8, 9, 13 (sin documentar) | Documentar G1/G2/G3 y decidir qué parte es ejecutable sin GUI |

---

## 2. Definición del Bloque G

| Aspecto | Definición |
|---------|------------|
| **Objetivo** | Terminar la funcionalidad y los contratos técnicos de las fases 7, 8 y 9 (GUI funcional, experiencia mínima, flujos principales) sin entrar en diseño visual. |
| **G1 — GUI funcional** | `WelcomeScreen`, `OnboardingShell`, `Home`, `ViewRouter`, `SettingsShell` y `WorkbenchSidebar` funcionan. No se reorganizan menús ni se cambian iconos. |
| **G2 — Experiencia mínima** | Un usuario puede: crear perfil local, completar onboarding, llegar a Home, abrir Configuración y Soporte, activar Modo Desarrollador, cerrar sesión y retomar. |
| **G3 — Flujos principales** | Login local funcional, sesión persistente, onboarding persistente, acceso a settings, soporte y diagnóstico, sin integraciones OAuth reales. |
| **Exclusiones** | Rediseño visual, animaciones, iconografía, accesibilidad, identidad visual, reorganización cosmética. |
| **Dependencias** | Contratos de sesión, identidad local, permisos, persistencia, sidecar health, build ID. |
| **Tests** | `npm test`, `npm run build`, sidecar smoke, `cargo test`, `cargo clippy`, `cargo fmt`. |
| **Criterios de salida** | Flujos funcionan sin intervención manual; tests verdes; sin P0/P1; build no promocionado; GUI no declarada aprobada. |
| **Riesgos** | Contaminar `feature/normal-user-experience`; reintroducir deuda visual; bloquear progreso técnico por validación manual prematura. |

---

## 3. P0/P1 abiertos o sospechosos

| ID | Prioridad | Descripción | Ubicación | Estado |
|----|-----------|-------------|-----------|--------|
| F14-BACKEND-001 | P1 | `/api/support` no exporta diagnóstico | `sidecar/routers/support.py` (parcial) | PENDIENTE técnico |
| F14-LOG-001 | P2 | Logs del sidecar no incluyen `build_id` en cada línea | `sidecar/main.py` | PENDIENTE técnico |
| F14-ZIP-001 | P2 | No se genera paquete ZIP de diagnóstico con manifest, hashes y logs | `scripts/validate-diagnostic-package.ps1` | PENDIENTE técnico |
| IDENTITY-LOCAL-001 | P2 | Perfil local requiere contrato de recovery más duro | `sidecar/repositories/local_profile_repository.py` | PROBADO parcial |
| IDENTITY-OAUTH-001 | P2 | Google/Microsoft requieren `client_id` real | config/env | BLOQUEADO EXTERNAMENTE |

No hay P0/P1 confirmados activos en la rama actual. Los P1/P2 anteriores (`INSTALL-BUILD-001`, `BUILD-LIFE-001`) están corregidos.

---

## 4. Líneas de trabajo paralelo

### Línea A — validación manual (congelada)

- Build: `internal-alpha-20260805-229cf37`.
- Checklist: `docs/validation/FASE14_GUI_MANUAL_CHECKLIST.md`.
- No modificar artefactos, manifest, Build ID ni evidencia.
- No promover releases.
- Veredicto cambiará solo cuando un operador humano complete el checklist.

### Línea B — desarrollo técnico (autorizada)

- Rama: `feature/technical-phase-completion`.
- Puede avanzar siempre que:
  - no cambie el build congelado;
  - no publique release;
  - no declare evidencia visual inexistente;
  - no agregue cambios cosméticos;
  - respete el Feature Freeze UX.

---

## 5. Orden de prioridad de trabajo técnico

### Prioridad 1 — P0/P1 confirmados
Ninguno activo. Si aparecen, detenerse y corregir.

### Prioridad 2 — Deuda técnica FASE 14
1. `endpoint /api/support` que genere ZIP de diagnóstico con:
   - `summary.json`
   - `manifest.json`
   - `system.txt`
   - `events.jsonl`
   - `README.txt`
   - `SHA256SUMS.txt`
   - `logs/` directory
2. Incluir `build_id` en cada línea de log.
3. Validar ZIP contra `scripts/validate-diagnostic-package.ps1`.

### Prioridad 3 — Arquitectura de identidad
- Sesión: contrato durable, local, OAuth stubs.
- Permisos: grants, roles.
- Profile Store: recovery, idempotencia.
- Account Linking: contrato ya implementado.

### Prioridad 4 — Pruebas y reproducibilidad
- Ejecutar suite completa `python -m pytest -q` en rama técnica.
- `npm test` y `npm run build`.
- `cargo test`, `cargo clippy`, `cargo fmt`.

### Prioridad 5 — Rendimiento
- `time-to-ready`, startup, RAM/CPU idle, fugas de procesos/puertos.

### Prioridad 6 — Interfaz
No trabajar. Congelada.

---

## 6. Rama recomendada

Creada y en uso:

```text
feature/technical-phase-completion
```

Origen: `feature/normal-user-experience` (a930c4e) en lugar de `main`, porque `main` no contiene los contratos técnicos de identidad, OAuth y rate limiting implementados en `feature/normal-user-experience`.

Decisión de contenido:

- Conservar todo el trabajo técnico: `OAuthTransactionStore`, `LocalProfileRepository`, `AccountLinkingService`, `RateLimiter`, `OnboardingShell` funcional.
- No agregar nuevas vistas, iconos, colores ni reorganización menú.
- `feature/normal-user-experience` queda como referencia; no crecerá con fases nuevas.
- No merge automático.

---

## 7. Próxima acción inmediata

**Implementar el backend de diagnóstico de FASE 14.**

- Tarea: `sidecar/routers/support.py` — endpoint `/api/support/diagnostic` que genere el paquete ZIP.
- No requiere GUI.
- No requiere validación manual.
- No requiere secretos reales.
- Es headless testeable.
- Reduce deuda técnica de FASE 14.

### Criterio GO/NO-GO

- **GO** si la tarea genera un ZIP válido para `scripts/validate-diagnostic-package.ps1` y los tests nuevos pasan.
- **NO GO** si aparece P0/P1, pérdida de datos o fuga de secretos.
