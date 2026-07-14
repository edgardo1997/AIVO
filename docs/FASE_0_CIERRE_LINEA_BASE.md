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

La fase 0 queda cerrada. La siguiente fase es restaurar build, contratos y calidad básica.
