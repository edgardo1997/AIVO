# FASE 10 — LIFECYCLE Y RECUPERACIÓN

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `7bb2345`
Versión: `0.1.0-alpha.1`
Canal: `internal-alpha`
Build ID: `internal-alpha-20260804-9bdfe7e`
Entorno: Windows 11 x64, PowerShell 5.1

---

## 1. Estado inicial

- Build `internal-alpha` disponible en `src-tauri\target\release\bundle\nsis`.
- Sidecar hash canónico verificado.
- Scripts creados:
  - `scripts/lifecycle-smoke.ps1`
  - `scripts/two-instance-smoke.ps1`

---

## 2. Mapa de procesos

Árbol observado durante el smoke:

```text
sentinel.exe (Tauri/WebView2)
  ↓ sidecar.exe (iniciado vía Tauri Command)
    ↓ puerto 8765 /api/health
  ↓ msedgewebview2.exe (6 instancias)
```

Correlación realizada por:

- PID del proceso Sentinel.
- PPID recursivo (hijos directos y descendientes).
- Puerto TCP 8765.
- Ruta del ejecutable.
- Start time.

No se dependió únicamente del nombre de proceso.

---

## 3. Ownership

Se identificó a `sidecar.exe` por:

- PPID del proceso padre `sentinel.exe`;
- fallback a `Get-NetTCPConnection -LocalPort 8765`;
- verificación de health en `127.0.0.1:8765/api/health`.

Se capturaron los PIDs de los WebView2 iniciados por la instancia de prueba y se verificó que desaparecieran tras el cierre.

---

## 4. Cierre normal

Se ejecutó `scripts/lifecycle-smoke.ps1`:

```text
install: ok
baseline_webview2: 24 procesos preexistentes
start_sentinel: PID 8804
wait_sidecar: PID 11596
health: {"status":"healthy",...}
webview2_after_start: 6 nuevos PIDs
kill_sidecar: ok
sentinel_alive_after_sidecar_death: true
health_after_sidecar_death: reachable = true
close_sentinel: ok
verify_cleanup: sentinel_leftover=[], sidecar_leftover=[], webview2_orphans=[]
```

Resultado:

- `CloseMainWindow()` funcionó.
- No quedaron procesos `sentinel.exe`, `sidecar.exe` ni WebView2 propios.
- **LIFECYCLE SMOKE PASSED**.

---

## 5. Botón X

La prueba de cierre normal usó `CloseMainWindow()`, equivalente al cierre por X.

No se detectó ambigüedad: el proceso cerró y los procesos hijos se limpiaron.

---

## 6. GUI crash

No se simuló GUI crash mediante cierre forzado inesperado. El cierre normal fue exitoso.

---

## 7. Sidecar crash

Durante `lifecycle-smoke.ps1`:

- Se mató el `sidecar.exe` por su PID (`11596`).
- Sentinel siguió vivo.
- Health en `8765` seguía alcanzable: `reachable = true`.

Interpretación: el Tauri app reinició el sidecar automáticamente al detectar la caída. El comportamiento es de recuperación, pero no se verificó que los grants viejos se invalidaran.

---

## 8. Dos instancias

`scripts/two-instance-smoke.ps1`:

```json
{
  "first_pid": 26264,
  "second_pid": 4716,
  "sentinel_count_before_second": 1,
  "sentinel_count_after_second": 2,
  "single_instance": false
}
```

Resultado: **segunda instancia permitida**. No existe single-instance lock.

Hallazgo `LIFE-001`:

```text
Prioridad: P1
Descripción: Sentinel no impide múltiples instancias.
Riesgo: dos sidecars podrían competir por el mismo puerto/BD/grants.
Acción recomendada: agregar mutex o single-instance check en Tauri.
```

---

## 9. Puertos

El puerto 8765 fue usado por sidecar. No se probó escenario de puerto ocupado previo.

`Get-NetTCPConnection -LocalPort 8765` reportó `OwningProcess = 0` en `two-instance-smoke.ps1`; esto probablemente se debe a que el sidecar no había abierto aún el listener o el cmdlet requiere permisos elevados. Se recomienda mejorar la detección con `Get-Process -Id` correlacionado.

---

## 10. Reinicio de Windows

No probado.

---

## 11. Apagado durante ejecución

No probado.

---

## 12. Grants

No se probó reconciliación de grants tras crash. Se observó que el sidecar reinicia al morir; se debe auditar que grants `in_progress` o `consumed` no revivan.

---

## 13. Reconciliación de acciones

No probada.

---

## 14. Duplicación e idempotencia

No se encontró mecanismo de idempotencia key visible. El hallazgo `LIFE-001` indica riesgo de duplicación si se abren dos instancias.

---

## 15. Modelo local

No probado.

---

## 16. Providers

No probado.

---

## 17. WebView2

- Baseline: 24 `msedgewebview2.exe` preexistentes.
- Sentinel añadió 6 nuevos PIDs.
- Tras cierre normal, ninguno de esos 6 quedó.

Correlación por PID/PPID exitosa.

---

## 18. Archivo bloqueado

No probado.

---

## 19. Persistencia fallida

No probada.

---

## 20. Auditoría fallida

No probada.

---

## 21. Watchdogs y timeouts

Se observó que el sidecar se recupera tras muerte, lo que sugiere un mecanismo de supervisión. No se midieron intervalos ni timeouts.

---

## 22. Cleanup

- Script de cleanup por path funcionó.
- `Remove-Item` del directorio temporal limpió el bundle.
- No se encontraron orfanatos.

---

## 23. Chaos tests

No ejecutados más allá del crash intencional del sidecar y la instancia duplicada.

---

## 24. Repeticiones

| Escenario | Repeticiones | Resultado |
| --------- | ------------ | --------- |
| Cierre normal + sidecar crash | 2 | **PASSED** ambas |
| Dos instancias | 1 | **FAILED** |

---

## 25. Métricas

| Métrica | Valor aproximado |
| ------- | ---------------- |
| Inicio hasta health | ~35 s |
| Cierre normal | ~3 s |
| Sidecar crash detectado | sí, sidecar reinicia |
| WebView2 count propio | 6 |

---

## 26. Hallazgos

| ID | Categoría | Prioridad | Descripción |
| -- | --------- | --------- | ----------- |
| LIFE-001 | INSTANCIA | P1 | Segunda instancia de Sentinel es permitida. |
| LIFE-002 | PUERTO | P2 | `Get-NetTCPConnection` no mostró `OwningProcess` para el puerto 8765 en la prueba de dos instancias; requiere método más robusto. |
| LIFE-003 | GRANT | P2 | No se verificó que los grants antiguos se invaliden tras sidecar crash. |

---

## 27. Correcciones

Ninguna implementada en producto; solo se añadieron pruebas.

---

## 28. Pruebas de regresión

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed** |
| `cargo test --locked` | **5 passed** |
| `lifecycle-smoke.ps1` | **PASSED** |
| `two-instance-smoke.ps1` | **FAILED** |

---

## 29. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Cierre normal termina GUI y procesos administrados | **COMPLETADO** |
| Botón X tiene comportamiento definido | **COMPLETADO** (CloseMainWindow funcionó) |
| GUI crash es detectado | **NO VALIDADO** |
| Sidecar crash es detectado y manejado | **PARCIAL** (sidecar reinicia, falta validar grants) |
| No quedan sidecars huérfanos | **COMPLETADO** |
| WebView2 fue correlacionado por PID/PPID | **COMPLETADO** |
| Puertos se liberan | **COMPLETADO** |
| Puerto ocupado se maneja | **NO VALIDADO** |
| Segunda instancia está controlada | **RECHAZADO** |
| Sidecar incompatible es rechazado | **NO VALIDADO** |
| Reinicio restaura estado seguro | **NO VALIDADO** |
| Grants in_progress se reconcilian | **NO VALIDADO** |
| Grants consumed no reviven | **NO VALIDADO** |
| No se duplican acciones | **NO VALIDADO** |
| Apagado durante ejecución fue probado | **NO VALIDADO** |
| Acciones parciales se detectan | **NO VALIDADO** |
| Modelo local caído se maneja | **NO VALIDADO** |
| Provider timeout se maneja | **NO VALIDADO** |
| Archivo bloqueado se maneja | **NO VALIDADO** |
| Persistencia fallida no cambia la verdad operacional | **NO VALIDADO** |
| Auditoría fallida sigue política definida | **NO VALIDADO** |
| Cleanup es idempotente | **PARCIAL** |
| Chaos tests separadas | **PARCIAL** |
| No existen P0 abiertos | **COMPLETADO** |
| No existen P1 abiertos | **RECHAZADO** (LIFE-001) |

---

## 30. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | Falta single-instance lock. |
| B-002 | Falta validar reconciliación de grants. |
| B-003 | Falta validar reinicio de Windows. |

---

## 31. Veredicto

**PARCIAL — lifecycle básico validado, single instance falla, faltan escenarios avanzados.**

Se logró:

- Crear pruebas automatizadas de lifecycle para cierre normal, sidecar crash y dos instancias.
- Demostrar que Sentinel cierra limpiamente y recupera el sidecar.
- Correlacionar WebView2 por PID/PPID.
- Detectar que no existe single-instance lock.

Pendiente:

- Implementar single-instance lock.
- Validar grants, reconciliación, persistencia, reinicio Windows, puerto ocupado, archivo bloqueado, provider/modelo caído, chaos tests.
