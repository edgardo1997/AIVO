# Fase 1 — Build y calidad reproducible

Fecha de cierre: 2026-07-14

## Objetivo

Convertir la línea base de la Fase 0 en un árbol de trabajo compilable, verificable y coherente antes de continuar con nuevas capacidades.

## Trabajo completado

- Corregidos los contratos TypeScript de memoria, identidad, presets y búsqueda de perfiles para que coincidan con las respuestas reales del sidecar.
- Corregida la pantalla de perfiles: los presets consumen su envoltorio de API y la búsqueda muestra perfiles en lugar de interpretar resultados como historial.
- Eliminados nombres indefinidos en rutas de ejecución, migración y sincronización offline.
- Sustituido el pseudoaleatorio de jitter por `SystemRandom`.
- Los fallos antes silenciados en rutas críticas ahora quedan registrados.
- Normalizado el código Python con Ruff y corregidos sus hallazgos de calidad y seguridad.
- Unificada la versión pública de frontend, Tauri y API en `1.0.0`.

## Puertas verificadas

| Puerta | Resultado |
| --- | --- |
| `npm run build` | Correcto |
| `npm test -- --run` | 115/115 pruebas correctas |
| `python -m ruff check sentinel sidecar` | Sin hallazgos |
| `python -m compileall -q sentinel sidecar` | Correcto |
| Pruebas Python focalizadas | 78/78 correctas |
| `cargo check --manifest-path src-tauri/Cargo.toml` | Correcto |

## Riesgos que continúan

- La suite Python completa debe estabilizarse y clasificarse en la fase de pruebas integrales; esta fase validó las rutas modificadas y los contratos principales.
- FastAPI informa de APIs de ciclo de vida obsoletas (`on_event`); no bloquea el producto actual, pero debe migrarse a `lifespan`.
- La cobertura funcional completa, pruebas E2E del instalador y endurecimiento de publicación pertenecen a fases posteriores.

## Criterio de salida

La Fase 1 queda cerrada cuando este documento y los cambios asociados están versionados en la rama `codex/phase-1-build-quality` y todas las puertas anteriores siguen en verde.
