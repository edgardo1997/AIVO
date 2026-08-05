# FASE 12 — VALIDAR INSTALACIÓN LIMPIA

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `51067ad`
Versión: `0.1.0-alpha.1`
Canal: `internal-alpha`
Build ID: `internal-alpha-20260804-9bdfe7e`

---

## 1. Artefactos

| Artefacto | Ruta | SHA-256 | Tamaño |
| --------- | ---- | ------- | ------ |
| NSIS installer | `src-tauri\target\release\bundle\nsis\Sentinel_0.1.0-alpha.1_x64-setup.exe` | ver build | ~35 MB |
| Sidecar canónico | `sidecar\dist\sidecar.exe` | `84DE8827212BCD6C4A763EC878DB8623C67BF08ECF22FB96A1CEE0F0B0594487` | — |

No se generó MSI en esta fase. `tauri.conf.json` y `tauri.release.conf.json` tienen `targets: ["nsis"]`.

---

## 2. Entornos limpios

No se dispuso de máquina virtual, Windows Sandbox, equipo secundario ni usuario nuevo.

La validación se ejecutó en el entorno de desarrollo con un directorio temporal `C:\Users\edgar\AppData\Local\SentinelSmoke` para aislar la instalación.

**Esto no reemplaza una VM limpia.**

---

## 3. Baseline del sistema

- Procesos Sentinel/Sidecar fueron detenidos antes de la prueba.
- No se encontraron carpetas `SentinelSmoke` previas.
- WebView2 presente en el sistema (baseline existente).

---

## 4. MSI

No probado. No se generó artefacto MSI.

---

## 5. NSIS

Se ejecutó `scripts/installer-smoke.ps1`:

```json
{
  "install": "ok",
  "hash_sidecar": "ok",
  "start": "ok",
  "health": "ok",
  "close": "ok",
  "uninstall": "ok",
  "residuals": "uninstaller left residuals"
}
```

Detalle de `hash_sidecar`:

```text
canonical: 84DE8827212BCD6C4A763EC878DB8623C67BF08ECF22FB96A1CEE0F0B0594487
installed: 84DE8827212BCD6C4A763EC878DB8623C67BF08ECF22FB96A1CEE0F0B0594487
```

El sidecar instalado coincide con el canónico.

---

## 6. Comparación

| Criterio | NSIS | MSI |
| -------- | ---- | --- |
| Instalación exitosa | Sí | N/A |
| Hash sidecar correcto | Sí | N/A |
| Health alcanzable | Sí | N/A |
| Cierre limpio | Sí | N/A |
| Desinstalación sin residuales | No | N/A |

---

## 7. Instalador oficial

Elegido: **NSIS**.

Motivo: único instalador generado por el pipeline canónico; MSI fue deshabilitado por problemas con el identificador de pre-release `alpha.1`.

---

## 8. Primer inicio

Se abrió `sentinel.exe` desde el directorio de instalación. La ventana se mostró y el sidecar arrancó automáticamente. Health respondió con `status: healthy`.

No se completó el onboarding interactivo.

---

## 9. WebView2

WebView2 estaba presente en el sistema. No se probó ausencia.

Se correlacionaron procesos `msedgewebview2.exe` por PID/PPID en fases anteriores.

---

## 10. Sidecar instalado

- Ruta: `C:\Users\edgar\AppData\Local\SentinelSmoke\sidecar\sidecar.exe`
- Hash: `84DE8827212BCD6C4A763EC878DB8623C67BF08ECF22FB96A1CEE0F0B0594487`
- Puerto: 8765
- Versión: `0.1.0-alpha.1`

Coincide con el sidecar canónico.

---

## 11. Datos creados

No se inspeccionaron `%APPDATA%` ni `%LOCALAPPDATA%` en detalle. Los datos del sidecar se crean en `SENTINEL_DATA_DIR` (`~/.sentinel` por defecto).

---

## 12. Onboarding

No se probó interactivamente.

---

## 13. Smoke funcional

Solo se verificó health del sidecar. No se envió mensaje desde GUI.

---

## 14. Cierre

El cierre de la GUI y la terminación de `sentinel.exe` funcionaron. Los procesos `sidecar` fueron detenidos explícitamente antes del desinstalador.

---

## 15. Reinicio

No probado.

---

## 16. Segundo inicio

No probado.

---

## 17. Desinstalación MSI

No aplica.

---

## 18. Desinstalación NSIS

Ejecutada con `uninstall.exe /S`. El instalador se eliminó, pero el directorio de instalación quedó como residual.

Hallazgo `INSTALL-001`:

```text
Prioridad: P2
Descripción: La desinstalación silenciosa deja residuales (al menos el directorio de instalación).
Posibles causas: proceso aún en uso, race en el uninstaller, /S no espera a limpieza completa.
Acción recomendada: auditar desinstalador NSIS, esperar/verificar en smoke, posiblemente requerir cierre forzado previo.
```

---

## 19. Residuales

Después del desinstalador:

```text
install_dir_leftover: true
process_residuals: []
```

No quedaron procesos Sentinel/Sidecar, pero el directorio `C:\Users\edgar\AppData\Local\SentinelSmoke` quedó. Se requirió limpieza manual.

---

## 20. Política de datos

No definida.

---

## 21. Reinstalación

No probada.

---

## 22. Upgrade y reparación

No probado.

---

## 23. Usuario estándar

No probado.

---

## 24. Rutas y perfiles

No probado.

---

## 25. Offline

No probado.

---

## 26. SmartScreen y firma

El instalador no está firmado (Alpha interna). SmartScreen mostrará advertencia.

No se ejecutó en VM con SmartScreen activo.

---

## 27. Logs

Reporte de smoke: `C:\Users\edgar\AppData\Local\Temp\installer-smoke-report.json`.

---

## 28. Rollback

No probado.

---

## 29. Procesos

Verificados por PID/PPID/path.

---

## 30. Repeticiones

| Escenario | Resultado |
| --------- | --------- |
| Instalación + hash + start + health | Sí |
| Desinstalación sin residuales | No |

---

## 31. Métricas

| Métrica | Valor aproximado |
| ------- | ---------------- |
| Instalación silenciosa | < 2 s |
| Inicio hasta health | ~30 s |
| Tamaño instalador | ~35 MB |
| Tamaño instalado | ~45 MB |

---

## 32. Hallazgos

| ID | Categoría | Prioridad | Descripción |
| -- | --------- | --------- | ----------- |
| INSTALL-001 | UNINSTALL | P2 | Desinstalación silenciosa deja residuales. |
| INSTALL-002 | ENV | P1 | No se probó en entorno limpio real (VM/Sandbox). |
| INSTALL-003 | MSI | P2 | No se generó ni probó instalador MSI. |

---

## 33. Correcciones aplicadas

- Nuevo `scripts/installer-smoke.ps1` para automatizar install/health/close/uninstall.

---

## 34. Pruebas de regresión

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed** |
| `cargo test --locked` | **5 passed** |
| `installer-smoke.ps1` | **Residuales detectados** (P2) |

---

## 35. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| MSI probado desde entorno limpio | **RECHAZADO** (no generado) |
| NSIS probado desde entorno limpio | **PARCIAL** (entorno dev, dir temporal) |
| Instalador oficial elegido | **COMPLETADO** (NSIS) |
| Hash sidecar coincide | **COMPLETADO** |
| Instalación termina correctamente | **COMPLETADO** |
| UAC documentado | **NO VALIDADO** |
| SmartScreen documentado | **PARCIAL** |
| Accesos directos funcionan | **NO VALIDADO** |
| Primer inicio funciona | **PARCIAL** (health OK) |
| WebView2 validado | **NO VALIDADO** |
| Sidecar inicia automáticamente | **COMPLETADO** |
| Datos en rutas correctas | **NO VALIDADO** |
| Cierre normal no deja procesos | **COMPLETADO** |
| Reinicio probado | **NO VALIDADO** |
| Segundo inicio funciona | **NO VALIDADO** |
| Desinstalación elimina binarios | **PARCIAL** (deja directorio) |
| Residuales clasificados | **PARCIAL** |
| Política de datos definida | **NO VALIDADO** |
| Reinstalación funciona | **NO VALIDADO** |
| Usuario estándar probado | **NO VALIDADO** |
| Perfiles Unicode probados | **NO VALIDADO** |
| Offline probado | **NO VALIDADO** |
| P0 abiertos | **N/A** |
| P1 abiertos | **RECHAZADO** (INSTALL-002 sin VM limpia) |

---

## 36. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | Falta entorno limpio (VM/Sandbox) para validar realmente. |
| B-002 | Desinstalador NSIS deja residuales; requiere investigación. |
| B-003 | MSI no se generó; no se pudo comparar con NSIS. |

---

## 37. Cambios pospuestos

- Probar MSI.
- Validar en VM/Sandbox.
- Smoke funcional desde GUI.
- Reinstalación y upgrade.
- Usuario estándar y perfiles Unicode.

---

## 38. Veredicto

**PARCIAL — instalación NSIS funciona, hash coincide, health alcanzable, pero desinstalación deja residuales y no se probó en entorno limpio real.**

Se logró:

- Generar y validar instalador NSIS canónico.
- Verificar que el sidecar instalado coincide con el canónico.
- Automatizar install/start/health/close/uninstall.
- Elegir NSIS como instalador oficial Alpha.

No se logró:

- Validar en entorno limpio real (VM, Sandbox, equipo secundario).
- Probar MSI ni comparar formatos.
- Completar onboarding y smoke funcional desde GUI.
- Verificar desinstalación sin residuales.

Recomendación: ejecutar FASE 12 en una VM limpia con `scripts/installer-smoke.ps1` y auditar el desinstalador NSIS para residuales.
