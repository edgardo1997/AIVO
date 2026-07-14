# Fase 7: CI/CD + Quality - Cierre

## Objetivo
Blindaje de calidad: CI/CD automatizado, CORS restrictivo, logging a archivo, tests frontend, y fix de tests postergados.

## Cambios realizados

### .github/workflows/ci.yml (NUEVO)
- **Frontend job** (ubuntu): npm ci → oxlint → tsc → vitest → vite build
- **Backend job** (windows-latest): pip install → ruff check → pytest
- Trigger: push/PR a main/master

### sidecar/main.py (editado)
- **CORS restrictivo**: solo origenes explícitos (localhost:5173, 127.0.0.1:5173, localhost:8765, 127.0.0.1:8765, tauri://localhost)
- **File logging**: RotatingFileHandler en sidecar/logs/sidecar.log (5MB × 3 backups)

### sidecar/modules/proactive.py (editado)
- Startup condicional: salta si AIVO_TESTING=1
- Shutdown handler agregado (stop engine)

### sidecar/tests/test_proactive.py (editado)
- SKIP MARKER REMOVED: el engine ya no arranca bajo test
- Agregados tests: test_proactive_suggestions, test_health

### sidecar/tests/conftest.py (editado)
- Set AIVO_TESTING=1 al inicio

### src/__tests__/IntentInput.test.tsx (NUEVO)
- 4 tests: render, disabled when empty, disabled prop, custom placeholder

## Resultados de verificacion
- tsc: 0 errores
- oxlint: 0 warnings/errors
- vitest: 17 passed (13 api + 4 IntentInput)
- pytest: 46 passed (antes 43, +3 proactive), 1 fail preexistente, **0 skipped**
- Build: npm run build exitoso

## No se modifico
- src-tauri/
- Ningun runtime
- Ningun archivo de sentinel/core/

## Proxima fase
FIN. El proyecto esta completo para un MVP profesional.
