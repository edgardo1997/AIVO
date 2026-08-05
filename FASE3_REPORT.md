# FASE 3 — BLOQUEOS CONSTITUCIONALES

Fecha: 2026-08-04
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit inicial: `69f1e9b`
Commit final: `2793285`
Fuente de verdad: `https://github.com/edgardo1997/AIVO.git` (`main`)

---

## 1. Estado inicial

El repositorio estaba limpio tras Fase 2 (`69f1e9b`). Working tree sin cambios. Todas las versiones y lockfiles estaban fijados.

Comandos base:

```text
git status --short  -> clean
git branch --show-current -> main
git rev-parse HEAD -> 69f1e9b551b10ecad65847b0a15ca8aaa2dd361b
git log --oneline -5 -> 69f1e9b .. 0f96b0a
```

---

## 2. Brechas reproducidas

Se identificaron tres brechas principales:

1. **Integration tools sin PathGuardian**: `DesktopIntegrationService` usaba `Path(raw).expanduser().resolve()` y `exists()` como única validación antes de `os.startfile`, `subprocess.Popen`, `explorer.exe` o visor de imágenes.
2. **TOCTOU en `filesystem.copy`**: `copy_file` validaba `source` y luego llamaba `shutil.copy2` sin revalidar la identidad del recurso.
3. **Verificación imprecisa**: `document.open`, `ide.open`, `os.reveal`, `browser.open` retornaban `opened: true` como si la operación estuviera verificada.

---

## 3. Integration tools auditadas

| Tool | Path local | PathGuardian | Efecto | Evidencia actual |
| ---- | ---------- | ------------ | ------ | ---------------- |
| `document.open` | Sí | Sí (`validate_open`) | `os.startfile` | `dispatched` + audit |
| `ide.open` | Sí | Sí (`validate_open`) | `subprocess.Popen([code, ...])` | `dispatched` + pid |
| `image.open` | Sí | Sí (`validate_open`) | `os.startfile` | `dispatched` + audit |
| `os.reveal` | Sí | Sí (`validate_open`) | `subprocess.Popen([explorer, ...])` | `dispatched` + pid |
| `browser.open` | No (URL) | No aplica | `webbrowser.open` | `dispatched` + browser_accepted |
| `image.inspect` | Sí | Sí (`validate_open`) | lectura de metadatos | `effect_observed` |

---

## 4. PathGuardian

- Se agregó `PathGuardian.validate_open(path, context)` en `sidecar/modules/security/path_guardian.py`.
- Normaliza, resuelve symlinks, verifica existencia, bloqueados, extensiones sensibles y traversal.
- No fuerza `path_is_within_allowed` para `open` (la política de bloqueo es suficiente para lectura/apertura en Alpha).

---

## 5. ResourceIdentity

- Nuevo archivo `sentinel/security/resource_identity.py`.
- Campos: `normalized_path`, `size`, `mtime_ns`, `ctime_ns`, `file_id`, `volume_id`, `is_symlink`, `is_junction`, `content_hash`, `hash_algorithm`, `captured_at`.
- Niveles:
  - `fast`: metadatos (`size`, `mtime`, `ctime`, `file_id` si está disponible).
  - `strong`: además SHA-256 para archivos <= 250 MB.
- Comparación: primero `file_id` + `volume_id` + `size` + `mtime`. Fallback a `size` + `mtime` + `ctime` cuando no hay IDs.

---

## 6. Binding de grants

- `ExecutionGrantContext` mantiene `params_hash` e `identity_hash` existentes.
- `filesystem.copy` ahora incluye `source_identity` y `dest_identity` en el resultado.
- `filesystem.copy` revalida `source` justo antes de `shutil.copy2` usando `ResourceIdentity`.
- Grants antiguos sin `ResourceIdentity` no son detectados explícitamente aún; no se reutilizan porque el runtime actual los emite a nivel de plan.

---

## 7. TOCTOU

- `DesktopIntegrationService.open_file`, `open_ide`, `reveal_path` capturan `ResourceIdentity` y revalidan inmediatamente antes del efecto del sistema operativo.
- `filesystem.copy` captura `source_identity` tras `validate_read`, revalida antes de `shutil.copy2` y captura `dest_identity` tras la copia.
- Si cambia `size`, `mtime`, `file_id`, `volume_id` o `content_hash`, la ejecución falla con `resource_changed_after_approval`.

---

## 8. VerificationLevel

- Se agregó `VerificationLevel` (`requested`, `dispatched`, `executed`, `effect_observed`, `verified`) en `sentinel/core/tool.py`.
- `ToolResult` ahora incluye `verification_level`.
- `document.open`, `ide.open`, `image.open`, `os.reveal`, `browser.open` reportan `dispatched`.
- `image.inspect` reporta `effect_observed`.
- `filesystem.copy` reporta `verified` tras comprobar tamaño y hash.

---

## 9. Verificación por tool

| Tool | Nivel máximo | Justificación |
| ---- | ------------ | ------------- |
| `filesystem.copy` | `verified` | destino existe, tamaño coincide, hash coincide |
| `filesystem.mkdir` | `verified` | directorio existe y es directorio |
| `document.open` | `dispatched` | OS aceptó el dispatch |
| `ide.open` | `dispatched` | proceso iniciado, pid retornado |
| `image.open` | `dispatched` | OS aceptó el dispatch |
| `os.reveal` | `dispatched` | Explorer aceptó el dispatch |
| `browser.open` | `dispatched` | navegador aceptó el URL |
| `image.inspect` | `effect_observed` | metadatos leídos correctamente |

---

## 10. Auditoría y verdad operacional

- `filesystem.copy` mantiene `_log` con status `resource_changed` para TOCTOU.
- Los mensajes de integración ahora distinguen:
  - "La solicitud para abrir el documento fue aceptada por Windows." (dispatch)
  - "La copia fue creada y verificada." (copy)
- No se implementó un motor de auditoría separado con eventos `dispatch_failed` / `verification_failed`; se usan los mecanismos existentes.

---

## 11. Compatibilidad y migración

- `ToolResult` añade `verification_level: Optional[str] = None` con default. No rompe compatibilidad.
- `DesktopIntegrationService.__init__` ahora acepta `guardian` opcional con default.
- Los tests anteriores `test_desktop_integrations.py` y `test_pdf_demo_e2e.py` siguen pasando.
- `sentinel/security/__init__.py` no se modificó para exportar `ResourceIdentity` aún.

---

## 12. Archivos modificados

- `sentinel/core/integrations.py`
- `sentinel/core/tool.py`
- `sentinel/security/resource_identity.py` (nuevo)
- `sentinel/tools/integration_tools.py`
- `sidecar/modules/security/path_guardian.py`
- `sidecar/services/filesystem_service.py`
- `sidecar/tests/test_toctou.py` (nuevo)

---

## 13. Pruebas añadidas

- `sidecar/tests/test_toctou.py`:
  - `ResourceIdentity` igual/diferente.
  - `ResourceIdentity` cambio por tamaño, mtime, ctime, hash.
  - `filesystem.copy` rechaza `source` modificado.
  - `filesystem.copy` rechaza `source` reemplazado.
  - `document.open` pasa PathGuardian y no reporta `verified`.
  - `document.open` rechaza archivo modificado.
  - `ide.open` rechaza path inexistente.
  - `os.reveal` rechaza path bloqueado.

Todas marcas con `@pytest.mark.alpha_constitutional_gate`.

---

## 14. Pruebas adversariales

Cobertura parcial:

- Reemplazo de source con mismo nombre.
- Cambio de contenido entre aprobación y ejecución.
- Path bloqueado.

No se probaron: symlinks, junctions, hard links, ADS, UNC, `\\?\`, `\\.\`, long paths, Unicode, trailing dot/space, archivos ocultos, permisos denegados. El entorno `tmp_path` de pytest no cubre todos esos casos.

---

## 15. Rendimiento

No se midió rendimiento de `ResourceIdentity`. No se implementó política de hash basada en tamaño con datos reales. Se mantiene el límite de 250 MB para hash SHA-256.

---

## 16. Gates constitucionales

Comando:

```text
python -m uv run python -m pytest -m alpha_constitutional_gate -q
```

Resultado:

```text
217 passed, 2984 deselected, 27 warnings in 31.27s
```

---

## 17. Build y smoke compilado

Comandos:

```text
cd sidecar
python -m uv run pyinstaller sidecar.spec --noconfirm
```

Resultado:

```text
INFO Build complete! The results are available in: ...\sidecar\dist
```

```text
cargo test --locked --manifest-path src-tauri/Cargo.toml
```

Resultado:

```text
5 passed; 0 failed
```

---

## 18. Cambios deliberadamente no realizados

- No se agregó una arquitectura de auditoría paralela.
- No se calculan hashes SHA-256 para archivos > 250 MB automáticamente.
- No se crearon archivos de configuración `development`/`test`/`alpha` separados.
- No se reescribió `ExecutionGrantContext` (se reutilizó con metadatos añadidos a resultados).
- No se implementó migración explícita de grants antiguos.
- No se añadió CI.

---

## 19. Limitaciones

- `ResourceIdentity.file_id`/`volume_id` dependen de `os.lstat` y pueden estar vacíos en algunos sistemas de archivos Windows; el fallback usa `ctime_ns`.
- `is_junction` es mejor esfuerzo; no detecta todos los reparse points.
- Las pruebas adversariales de Windows no están completas.
- No se validó `npm run tauri:build` ni empaquetado final con firma.

---

## 20. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| `document.open` pasa por PathGuardian | **COMPLETADO** |
| `ide.open` pasa por PathGuardian | **COMPLETADO** |
| `os.reveal` pasa por PathGuardian | **COMPLETADO** |
| `image.open` pasa por PathGuardian | **COMPLETADO** |
| `browser.open` valida URLs (no paths locales) | **COMPLETADO** (sin cambios) |
| Validación usa el path autorizado | **COMPLETADO** |
| `ResourceIdentity` definida | **COMPLETADO** |
| Grants sensibles incluyen `ResourceIdentity` vía resultados | **PARCIAL** |
| `filesystem.copy` revalida source | **COMPLETADO** |
| `filesystem.copy` revalida destination | **COMPLETADO** (identidad destino capturada) |
| `document.open` revalida el archivo | **COMPLETADO** |
| TOCTOU produce rechazo seguro | **COMPLETADO** |
| Grants antiguos inseguros no se reutilizan | **PARCIAL** (no hay mecanismo de migración) |
| `VerificationLevel` implementado | **COMPLETADO** |
| `document.open` no afirma apertura verificada | **COMPLETADO** |
| Auditoría distingue dispatch/efecto/verificación | **PARCIAL** (mensajes mejorados) |
| Mensajes reflejan evidencia real | **COMPLETADO** (dispatch/verificado) |
| Pruebas adversariales pasan | **PARCIAL** (cobertura parcial) |
| Gates constitucionales pasan | **COMPLETADO** |
| Build del sidecar pasa | **COMPLETADO** |
| No se agregaron funciones nuevas | **COMPLETADO** |

---

## 21. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | CI de reproducibilidad no configurada. |
| B-002 | Pruebas adversariales de Windows incompletas. |
| B-003 | `tauri:build` y empaquetado final no validados. |
| B-004 | Política de hash basada en medición no implementada. |
| B-005 | Migración de grants antiguos sin `ResourceIdentity` no definida. |

---

## 22. Veredicto

**PARCIAL — bloques constitucionales principales cerrados.**

Sentinel ahora exige que `document.open`, `ide.open`, `image.open` y `os.reveal` pasen por `PathGuardian`, capturen la identidad del recurso y revaliden inmediatamente antes del efecto del sistema operativo. `filesystem.copy` detecta cambios TOCTOU y reporta identidad del destino. `VerificationLevel` distingue `dispatched` de `verified`.

No se declara **COMPLETADO** porque faltan pruebas adversariales exhaustivas de Windows, medición de rendimiento de hash, CI y validación del build completo de Tauri.
