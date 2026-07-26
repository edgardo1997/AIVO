# Fase 13 — Consolidación y línea base

Fecha de cierre técnico: 25 de julio de 2026.

## Estado verificable

- Inventario final: 333 entradas en `git status`.
- Cambios en índice: 8.
- Cambios tracked fuera del índice: 98.
- Archivos untracked: 227.
- Eliminación intencional pendiente: `src/api.ts`, reemplazado por el paquete
  modular `src/api/`.
- No se realizó commit ni se descartaron cambios del usuario.

## Clasificación del worktree

### Válidos y activos

- `sentinel/`: contratos V1/V2, fronteras pasivas, observabilidad y correcciones
  del runtime existente cubiertas por pruebas.
- `sidecar/`: APIs, persistencia, migraciones y pruebas de caracterización,
  integración, seguridad, E2E y rendimiento.
- `src/`: migración de la API monolítica a `src/api/`, tipado y compatibilidad
  de frontend.
- `src-tauri/`: código y esquemas que compilan y pasan las validaciones Rust.
- `docs/`: arquitectura, auditorías y hoja de ruta.

### Compatibilidad mantenida

- Los contratos versionados y adaptadores legacy permanecen separados del
  runtime productivo.
- Los modelos V1 y V2 con nombres próximos no se eliminaron cuando representan
  etapas distintas del flujo o compatibilidad explícita.
- Los tests E2E que levantan el binario real requieren
  `SENTINEL_RUN_REAL_E2E=1`; la suite normal no inicia servicios reales.

### Duplicados consolidados

- La API frontend usa `src/api/` como frontera modular; `src/api.ts` queda
  obsoleto y marcado para eliminación.
- Los resultados no autoritativos comparten los contratos centrales exportados
  desde `sentinel/contracts`.
- Las comprobaciones AST distinguen contratos con nombres como
  `tool_gateway_decision_result_v1` de imports productivos reales.

### Candidatos obsoletos que requieren revisión posterior

- Alias y adaptadores legacy conservados por compatibilidad: no deben eliminarse
  hasta que exista un cutover autorizado y pruebas de consumidores.
- Reportes históricos de fases: son evidencia documental, no runtime; se
  recomienda archivarlos en una fase separada en vez de borrarlos aquí.
- Cambios untracked de V2: quedan clasificados como trabajo válido en curso,
  pero todavía necesitan una estrategia de commits por dominio.

## Gates

- Python global, pasada 1: 2763 passed, 14 skipped.
- Python global, pasada 2: 2763 passed, 14 skipped.
- Ruff: verde.
- Frontend tests: 129 passed.
- Frontend build: verde.
- Rust fmt/check/test: verde; 4 tests.
- `git diff --check`: debe permanecer limpio antes de crear la línea base Git.

## Recuperación

La recuperación actual está basada en el worktree y el índice existentes. Para
convertirla en un punto Git recuperable falta una acción deliberada del usuario:
revisar la división por dominios y autorizar uno o varios commits. Hasta entonces
no debe usarse `reset`, `clean` ni eliminación masiva de archivos untracked.
