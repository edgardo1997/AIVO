# FASE 13 — RENDIMIENTO Y ESTABILIDAD

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `999cb9c`
Versión: `0.1.0-alpha.1`
Canal: `internal-alpha`
Build ID: `internal-alpha-20260804-9bdfe7e`
Entorno: Windows 11 x64, 16 vCPU/32 GB (lógicos)

---

## 1. Baseline del sistema

No se midió baseline del sistema completo. Se asumió entorno de desarrollo con otras cargas.

## 2. Árbol de procesos

Sentinel principal inicia `sidecar.exe` y varios `msedgewebview2.exe`. Cada ciclo generó 10–13 PIDs relacionados.

## 3. Herramientas de medición

- PowerShell `Get-Process` para RAM y CPU.
- `Get-CimInstance Win32_ComputerSystem` para núcleos lógicos.
- `Invoke-RestMethod` para `/api/health`.
- `scripts/performance-smoke.ps1`.

## 4. Time-to-window

No se midió visualmente. Se usa `time_to_process_ms` como proxy.

## 5. Time-to-ready

Medido desde `Start-Process` hasta `health` HTTP en 3 ciclos:

| Ciclo | Time-to-process (ms) | Time-to-ready (ms) | Close (ms) |
| ----- | --------------------:| ------------------:| ----------:|
| 1     | 807                  | 50 019             | 12 056     |
| 2     | 22                   | 41 091             | 12 043     |
| 3     | 12                   | 38 024             | 12 034     |

Media time-to-ready: `43 045 ms`.

## 6. Sidecar startup

El sidecar arrancó automáticamente en cada ciclo. Tiempo incluido en time-to-ready.

## 7. Modelo local

No se probó con modelo local real.

## 8. RAM idle

Muestras cada 5 s durante 60 s tras el primer inicio:

| t (s) | Working Set (MB) | Private (MB) | PIDs | CPU % |
| ----: | ---------------: | -----------: | ---: | ----: |
| 0     | 646.63           | 354.17       | 10   | 0.00  |
| 5     | 695.23           | 402.20       | 10   | 1.13  |
| 10    | 673.82           | 381.03       | 10   | 0.20  |
| 15    | 676.50           | 381.66       | 10   | 0.59  |
| 20    | 675.65           | 381.28       | 10   | 0.12  |
| 25    | 675.85           | 381.14       | 10   | 10   | 0.16  |
| 30    | 659.70           | 368.20       | 10   | 0.59  |
| 35    | 659.98           | 368.79       | 10   | 0.12  |
| 40    | 660.48           | 369.17       | 10   | 0.28  |
| 45    | 661.22           | 369.94       | 10   | 0.12  |
| 50    | 660.96           | 369.52       | 10   | 0.40  |
| 55    | 662.08           | 370.29       | 10   | 0.24  |

RAM se estabilizó en ~660 MB working set, ~370 MB private. No crecimiento continuo en 60 s.

## 9. CPU idle

CPU baja, < 1 % en reposo con pico del 1.13 % en t=5 s.

## 10–17. Conversación, cloud, planificación, consentimiento, ejecución, demo, settings

No probados en esta fase.

## 18. Sesión prolongada

No probada.

## 19. Aperturas y cierres

Se ejecutaron 3 ciclos. Todos alcanzaron `healthy`. Todos cerraron en ~12 s.

## 20. Reinicios

No probados.

## 21. Memoria

No se detectó fuga en 60 s de idle. Se requiere sesión más larga para conclusión.

## 22. Handles y threads

No medidos.

## 23. Procesos

No se acumularon procesos Sentinel entre ciclos (se limpiaron). En cada ciclo ~10–13 PIDs.

## 24. Puertos

No se midieron `TIME_WAIT`.

## 25. Cierre

Cierre ~12 s. No se atribuyó a componente específico.

## 26. Tamaño instalado

`installed_size_mb`: **92.36 MB**.

## 27. Logs

No se midió crecimiento.

## 28. Bases y stores

No se midió crecimiento.

## 29. Responsividad GUI

No medida.

## 30. Cancelación

No probada.

## 31. Errores repetidos

No probados.

## 32. Umbrales Alpha

| Métrica | Valor observado | Umbral tentativo |
| ------- | ---------------:| ----------------:|
| time-to-ready | ~43 s | < 60 s |
| idle RAM | ~660 MB WS, ~370 MB private | — |
| idle CPU | < 1 % | < 5 % |
| close | ~12 s | < 15 s |
| installed size | 92 MB | < 150 MB |

## 33. Regresiones

No aplica.

## 34. Hallazgos

| ID | Categoría | Prioridad | Descripción |
| -- | --------- | --------- | ----------- |
| PERF-001 | START | P2 | Time-to-ready de ~50 s en primer inicio; 38–41 s en ciclos posteriores. |
| PERF-002 | RAM | P2 | ~660 MB working set idle; puede ser alto para una app base sin modelo cargado. |
| PERF-003 | SCOPE | P3 | Fase no cubre conversación, demo PDF, sesión larga ni responsividad. |

## 35. Correcciones aplicadas

- Nuevo `scripts/performance-smoke.ps1`.

## 36. Pruebas de regresión

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed** |
| `cargo test --locked` | **5 passed** |
| `performance-smoke.ps1` | **datos recopilados** |

## 37. Métricas finales

```json
{
  "time_to_ready_ms_avg": 43045,
  "time_to_ready_ms_min": 38024,
  "time_to_ready_ms_max": 50019,
  "idle_working_set_mb_last": 662.08,
  "idle_private_mb_last": 370.29,
  "idle_cpu_pct_max": 1.13,
  "close_ms_avg": 12044,
  "installed_size_mb": 92.36
}
```

## 38. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Time-to-window medido | **NO VALIDADO** (usado time_to_process) |
| Time-to-ready medido | **COMPLETADO** |
| Arranque sidecar medido | **PARCIAL** (implícito) |
| Arranque modelo medido | **NO VALIDADO** |
| RAM idle medida | **COMPLETADO** |
| CPU idle medida | **COMPLETADO** |
| Conversación local medida | **NO VALIDADO** |
| Conversación cloud medida | **NO VALIDADO** |
| Planificación medida | **NO VALIDADO** |
| Ejecución medida por etapa | **NO VALIDADO** |
| Cierre medido | **COMPLETADO** |
| Tamaño instalado medido | **COMPLETADO** |
| 10 aperturas/cierres | **NO VALIDADO** (3 ciclos) |
| 3 reinicios | **NO VALIDADO** |
| 3 demos PDF | **NO VALIDADO** |
| Múltiples conversaciones | **NO VALIDADO** |
| Cambios settings | **NO VALIDADO** |
| Offline/online | **NO VALIDADO** |
| Sesión prolongada | **NO VALIDADO** |
| Sin crecimiento anormal RAM | **PARCIAL** (60 s) |
| Sin acumulación de procesos | **PARCIAL** (3 ciclos) |
| GUI responsive | **NO VALIDADO** |
| Logs con rotación | **NO VALIDADO** |
| Bases sin crecimiento inesperado | **NO VALIDADO** |

## 39. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | Falta probar conversación, demo PDF, settings, offline/online, sesión larga, múltiples ciclos. |
| B-002 | Time-to-ready de ~40–50 s puede requerir mejoras para Alpha. |

## 40. Veredicto

**PARCIAL — se obtuvo baseline de inicio/idle/cierre, pero faltan flujos reales, sesión prolongada y múltiples ciclos.**

Se logró:

- Automatizar 3 ciclos de inicio/idle/cierre con medición de time-to-ready, RAM idle, CPU idle y tamaño instalado.
- Estabilizar observaciones: ~660 MB WS idle, <1 % CPU, cierre ~12 s, time-to-ready ~43 s promedio.

Pendiente:

- Medir time-to-window visual.
- Probar con modelo local.
- Ejecutar conversaciones, planificación, demo PDF, settings.
- Sesión prolongada de 4–8 horas.
- 10 ciclos completos y 3 reinicios.
- Análisis de logs, bases, responsividad GUI y manejo de errores.
