# Fase 0 — Cierre de línea base y preservación

**Fecha:** 14 de julio de 2026  
**Rama:** `codex/phase-0-baseline`  
**Commit inicial preservado:** `555bff06082d10a02bccc581162f5abff2075dbf`

## Objetivo

Preservar el desarrollo acumulado de Sentinel antes de iniciar las correcciones de estabilización, separando código fuente de datos runtime y artefactos generados.

## Acciones completadas

- Se inventariaron 53 archivos modificados, 3 eliminados y 315 nuevos antes de aplicar exclusiones.
- Se revisaron 440 archivos de texto buscando formatos comunes de claves privadas, tokens y secretos.
- Las nueve coincidencias encontradas pertenecían a documentación o fixtures deliberados de pruebas de redacción.
- Se excluyeron bases SQLite, logs, cachés, temporales, benchmarks locales, reportes generados y artefactos de compilación.
- Se verificó que `cost_tracker.db`, `knowledge_base.db`, las bases del sidecar, logs y `tmp/` quedan ignorados.
- Se creó la rama de estabilización `codex/phase-0-baseline`.
- Se registró un snapshot de 353 archivos fuente/documentales, sin blobs superiores a 1 MB.
- Se verificó la integridad del repositorio con `git fsck`; no se detectó corrupción. Los objetos dangling son objetos no referenciados históricos y no afectan el commit actual.
- Se confirmó que Vite excluye `src-tauri/target/**` y que el workspace excluye `target`, `node_modules` y entornos virtuales de los watchers. Esto mitiga el error `EBUSY` observado bajo OneDrive.

## Elementos deliberadamente no registrados

- Bases de datos runtime.
- Logs.
- Binarios e instaladores.
- Directorios `dist`, `build` y `target`.
- Claves de firma y certificados.
- Aprobación real de pentest.
- Resultados locales de benchmark y análisis.

## Restauración

Para recuperar exactamente la línea base:

```powershell
git switch codex/phase-0-baseline
git reset --hard pre-beta-audit
```

El segundo comando es destructivo para cambios posteriores sin guardar y sólo debe utilizarse expresamente como operación de recuperación.

## Riesgo residual

El repositorio continúa físicamente dentro de OneDrive. Las exclusiones de watchers reducen el problema observado, pero la sincronización todavía puede interferir con archivos de compilación. Si reaparece `EBUSY`, la solución recomendada es clonar la rama en una ruta local no sincronizada, por ejemplo `C:\dev\Sentinel`, y conservar OneDrive sólo para documentos exportados o backups controlados.

## Criterios de salida

- [x] Estado del desarrollo preservado en un commit recuperable.
- [x] Rama de estabilización creada.
- [x] Datos runtime y artefactos excluidos.
- [x] Búsqueda de secretos realizada.
- [x] Mitigación de watchers verificada.
- [x] Integridad Git verificada.
- [x] Procedimiento de restauración documentado.

## Revalidación de estabilización — 18 de julio de 2026

La línea base se volvió a auditar después de los cambios acumulados en el
workspace. El estado inicial de esta revalidación era de **46 fallos**, 4
pruebas omitidas y 21 infracciones de lint Python.

### Correcciones aplicadas

- Restaurado el diagnóstico `system.health` de cuatro pasos: CPU, memoria,
  disco y procesos.
- Corregidos los resultados booleanos indeterminados del evaluador objetivo de
  riesgo y restaurados sus modificadores de contexto contractuales.
- El LLM permanece como asesor sin autoridad para aumentar o reducir el riesgo
  objetivo; además, ya no se consulta para decisiones triviales de bajo riesgo.
- El nivel `view` rechaza explícitamente modificaciones del sistema.
- Los análisis de sistema de solo lectura pueden ejecutarse sin una aprobación
  innecesaria cuando la simulación no detecta peligro.
- La reproducción de una acción almacenada y aprobada usa autorización interna
  de un solo uso, sin saltarse las políticas del `ToolGateway`.
- Restaurado el LRU de grounding con orden de acceso determinista, independiente
  de la resolución del reloj de Windows.
- Activadas las pruebas asíncronas de grounding y corregido su contrato de
  tiempo.
- Reducida la lectura de procesos de más de 12 segundos a aproximadamente 2
  segundos al eliminar una consulta costosa que no formaba parte del resultado
  necesario.
- Actualizadas pruebas antiguas que todavía otorgaban al modelo autoridad sobre
  decisiones de seguridad o mezclaban “acceso completo” con un flujo que exige
  confirmación.

### Evidencia reproducible

| Puerta | Comando | Resultado |
|---|---|---|
| Backend completo | `python -m pytest -q` | 1802 pasan, 1 omitida, 23 deseleccionadas |
| Lint Python | `python -m ruff check sentinel sidecar` | limpio |
| Lint frontend | `npm run lint` | limpio |
| Tests frontend | `npm test -- --run` | 125/125 |
| Build frontend | `npm run build` | limpio |
| Rust/Tauri | `cargo check --manifest-path src-tauri/Cargo.toml` | limpio |

### Excepciones no bloqueantes

- `test_proactive.py` omite una prueba porque no existe un endpoint V1 para
  sugerencias proactivas. No se añadió dicho endpoint porque esta fase prohíbe
  ampliar funcionalidades.
- Permanecen dos avisos de dependencias externas: la transición futura de
  Starlette `TestClient` hacia `httpx2` y una API de `reportlab` que quedará
  obsoleta en Python 3.14.
- El workspace continúa con numerosos cambios previos del usuario. Esta fase no
  los descartó, revirtió ni consolidó en un commit.

## Cierre actualizado

La Fase 0 queda cerrada con build, lint y pruebas verdes. La siguiente fase puede
trabajar sobre calidad y arquitectura desde una línea base verificable.
