# Fase 2 — Suite determinista y cobertura de integración

Fecha de cierre: 2026-07-14

## Objetivo

Hacer que las pruebas de Sentinel terminen de forma reproducible, operen únicamente sobre recursos temporales y produzcan evidencia útil para diagnóstico y CI.

## Cambios realizados

- Pytest sólo descubre `sidecar/tests` y `tests`; se excluyen explícitamente artefactos, dependencias y copias empaquetadas bajo `src-tauri/target`.
- Cada prueba tiene un timeout de 30 segundos y la suite muestra skips y las 15 pruebas más lentas.
- La suite se divide automáticamente en `unit`, `integration`, `security`, `e2e` y `performance`.
- Los 23 benchmarks quedan separados de la suite funcional y disponen de un timeout ampliado explícito.
- Las bases de datos de prueba usan un directorio temporal de sesión; los archivos de configuración usan `tmp_path` por prueba.
- Los clientes FastAPI compartidos se cierran mediante context manager.
- Las comprobaciones de disponibilidad de modelos no inspeccionan servicios instalados en la máquina anfitriona durante pruebas.
- Se detectan y terminan procesos hijo creados por la suite antes de declararla correcta.
- Se corrigieron pruebas que dependían de claves reales, del estado anterior del registro de agentes o del encabezado inseguro `X-User-Id`.
- La ejecución asíncrona de triggers ya no deja coroutines sin esperar cuando no existe un event loop activo.
- Advisory forma parte de la colección oficial mediante `tests/test_advisory.py`.
- CI ejecuta los cuatro grupos funcionales en matriz, publica JUnit y cobertura focalizada de orquestador, gateway, router de modelos y memoria operacional.

## Evidencia local

| Ejecución | Resultado | Duración |
| --- | --- | --- |
| Suite global, pasada 1 | 1.665 aprobadas, 1 skip, 23 benchmarks separados | 6:11 |
| Suite global, pasada 2 | 1.665 aprobadas, 1 skip, 23 benchmarks separados | 6:21 |
| Unitarias | 1.229 aprobadas, 1 skip | 2:47 |
| Integración | 180 aprobadas | 2:09 |
| Seguridad | 166 aprobadas | 0:10 |
| E2E | 90 aprobadas | 1:24 |
| Frontend | 115 aprobadas | 0:16 |
| Build frontend | Correcto | < 1 s |
| Ruff | Sin hallazgos | — |
| Cargo check | Correcto | 0:08 |

Los informes JUnit locales se generan como `.pytest-*.xml` y están excluidos de Git. CI conserva los equivalentes como artefactos por grupo junto con los informes XML de cobertura.

## Skips y advertencias visibles

- Existe un único skip: `test_proactive.py`, porque todavía no hay endpoint V1 para sugerencias proactivas.
- FastAPI mantiene advertencias de migración desde `on_event` hacia `lifespan`.
- ReportLab informa una obsolescencia interna compatible con la versión actual.
- No existen `xfail`; la configuración usa `xfail_strict = true`.

## Comandos oficiales

```text
npm run test:py
npm run test:py:unit
npm run test:py:integration
npm run test:py:security
npm run test:py:e2e
npm run test:py:performance
```

## Criterio de salida

La fase queda cerrada con dos pasadas globales consecutivas, los cuatro grupos funcionales independientes, frontend y Rust en verde, sin procesos `pytest` iniciados por estas ejecuciones después de su finalización.
