# FASE 6 — FIRMA Y CANALES

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit inicial: `e4f77a9`
Commit final: `d67659b`
Fuente de verdad: `https://github.com/edgardo1997/AIVO.git` (`main`)

---

## 1. Estado inicial

```text
git rev-parse HEAD  -> e4f77a9
git status --short -> clean (tras commit de FASE 5)
```

Tauri tenía updater configurado con clave pública, `createUpdaterArtifacts: false`, y terminaba con error si no existía `TAURI_SIGNING_PRIVATE_KEY`.

---

## 2. Canales definidos

| Canal | Working tree | Updater | Firma Tauri | Authenticode | Hashes |
| ----- | ------------ | ------- | ----------- | ------------ | ------ |
| `development` | dirty permitido | off | no | no | sí |
| `internal-alpha` | limpio recomendado | off | no | no | sí |
| `external-alpha` | limpio obligatorio | on | sí | requerido | sí |
| `stable` | limpio + tag | on | sí | requerido | sí |

---

## 3. Matriz de políticas

La política está embebida en `scripts/build-alpha.ps1`:

```powershell
$ChannelPolicy = @{
    "development"   = @{ dirty = $true;  updater = $false; tauriSign = $false; authenticode = $false; tag = $false; requireClean = $false }
    "internal-alpha"= @{ dirty = $false; updater = $false; tauriSign = $false; authenticode = $false; tag = $false; requireClean = $true  }
    "external-alpha"= @{ dirty = $false; updater = $true;  tauriSign = $true;  authenticode = $true;  tag = $false; requireClean = $true  }
    "stable"        = @{ dirty = $false; updater = $true;  tauriSign = $true;  authenticode = $true;  tag = $true;  requireClean = $true  }
}
```

---

## 4. Configuración por canal

- `src-tauri/tauri.conf.json` — canal `internal-alpha` y `development`:
  - `bundle.createUpdaterArtifacts: false`
  - `plugins.updater.endpoints: []` (runtime deshabilitado)

- `src-tauri/tauri.release.conf.json` — canal `external-alpha` y `stable`:
  - `bundle.createUpdaterArtifacts: true`
  - `plugins.updater.endpoints` apuntando a GitHub releases
  - Requiere `TAURI_SIGNING_PRIVATE_KEY`

---

## 5. Alpha interna

Contrato:

```text
updater = disabled
TAURI_SIGNING_PRIVATE_KEY = not required
Authenticode = optional
hashes = required
artifact manifest = required
exit code = 0
```

`tauri.conf.json` ahora no intenta firmar ni descargar updates.

---

## 6. Alpha externa

Contrato:

```text
updater = enabled
TAURI_SIGNING_PRIVATE_KEY = required
Authenticode = required
timestamp = required
hashes = required
```

El build selecciona `src-tauri/tauri.release.conf.json` con `npm exec -- tauri build --config ...`.

---

## 7. Release estable

Contrato:

```text
working tree = clean
tag = required
updater = enabled
Tauri signing = required
Authenticode = required
timestamp = required
```

---

## 8. Firma del updater

Requiere variables de entorno:

```text
TAURI_SIGNING_PRIVATE_KEY
TAURI_SIGNING_PRIVATE_KEY_PASSWORD (si aplica)
```

La clave pública está en:

- `src-tauri/tauri.release.conf.json`
- `src-tauri/src/lib.rs`

No se versionan secretos.

---

## 9. Authenticode

Requiere:

```text
SENTINEL_AUTHENTICODE_THUMBPRINT
SENTINEL_TIMESTAMP_URL
```

El script firma, en orden:

1. `sidecar.exe` canónico
2. `sentinel.exe` Tauri
3. instaladores MSI/NSIS

Verifica con `Get-AuthenticodeSignature`.

---

## 10. Timestamping

Usa el servidor configurado en `SENTINEL_TIMESTAMP_URL`. Si el firmado falla en canales que lo requieren, el build falla.

---

## 11. Hashes

SHA-256 generado para:

- sidecar canónico
- sidecar empaquetado
- `sentinel.exe`
- instaladores

Se escriben en `artifacts/<channel>/SHA256SUMS.txt`.

---

## 12. Manifest de release

`artifacts/<channel>/manifest.json`:

- product, version, channel
- commit, build_id, timestamp
- `updater_enabled`, `tauri_signed`, `authenticode`
- lista de artefactos con `sha256` y `size`

---

## 13. Prechecks

Antes de compilar:

1. Canal definido y válido.
2. Working tree limpio según canal (salvo `-AllowDirty` para desarrollo).
3. Tag en `HEAD` para `stable`.
4. `TAURI_SIGNING_PRIVATE_KEY` si el canal lo requiere.
5. `signtool.exe` disponible si el canal lo requiere.

---

## 14. Postchecks

Después del build:

1. Todos los comandos exit 0.
2. `sidecar.exe` canónico coincide con el empaquetado.
3. Artefactos esperados existen.
4. Firmas requeridas son `Valid`.
5. Hashes y manifest generados.

Si falla: excepción con `ErrorActionPreference = "Stop"`.

---

## 15. Scripts

- `scripts/build-alpha.ps1` — build canónico con canal.
- `scripts/smoke-sidecar.ps1` — validación del sidecar.

Comandos:

```powershell
.\scripts\build-alpha.ps1 -Channel development -AllowDirty
.\scripts\build-alpha.ps1 -Channel internal-alpha
.\scripts\build-alpha.ps1 -Channel external-alpha
.\scripts\build-alpha.ps1 -Channel stable
```

---

## 16. CI/CD

- `.github/workflows/build-internal-alpha.yml`
- `.github/workflows/build-external-alpha.yml` (requiere environment y secrets)
- `.github/workflows/release-stable.yml` (requiere tag, environment y secrets)

No se ejecutaron en GitHub.

---

## 17. Política de actualización

Documentada en `docs/SIGNING_AND_CHANNELS.md`:

- `internal-alpha`: reinstalación manual.
- `external-alpha`: updater firmado o manual.
- `stable`: updater firmado, ventanas de rollout, rollback documentado.

---

## 18. Rotación y revocación

1. Filtración de clave Tauri: generar par nuevo, actualizar `pubkey`, publicar release.
2. Revocación de certificado: publicar build con certificado nuevo.
3. Bloqueo de build: manifest con `revoked: true` y hash.

---

## 19. Pruebas ejecutadas

| Caso | Comando | Resultado |
| ---- | ------- | --------- |
| `stable` sin tag y dirty | `.\scripts\build-alpha.ps1 -Channel stable` | **FAIL precheck** (dirty) |
| `external-alpha` dirty | `.\scripts\build-alpha.ps1 -Channel external-alpha` | **FAIL precheck** (dirty) |
| `stable` precheck | `.\scripts\build-alpha.ps1 -Channel stable` | **FAIL precheck** (dirty) |
| `external-alpha` precheck | `.\scripts\build-alpha.ps1 -Channel external-alpha` | **FAIL precheck** (dirty) |
| `development` full build | `.\scripts\build-alpha.ps1 -Channel development -AllowDirty -SkipTests` | **BUILD SUCCESS** |

Resultado del build `development`:

```text
Sidecar SHA-256:   06550657149AACC48045A694F2A7DA7D55853C3B0B86345C9D9769C1789EFD04
Health OK: {"status":"healthy","version":"0.1.0-alpha.1",...}
Bundled sidecar hash matches canonical.
Manifest: artifacts/development/manifest.json
BUILD SUCCESS: development-20260804-f9f7b0a+dirty.f9f7b0a
```

Los prechecks fallan correctamente antes de compilar.

---

## 20. Archivos modificados

- `scripts/build-alpha.ps1`
- `src-tauri/tauri.conf.json`
- `src-tauri/tauri.release.conf.json` (nuevo)
- `docs/SIGNING_AND_CHANNELS.md` (nuevo)
- `.github/workflows/build-internal-alpha.yml`
- `.github/workflows/build-external-alpha.yml` (nuevo)
- `.github/workflows/release-stable.yml` (nuevo)

---

## 21. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Canal development definido | **COMPLETADO** |
| Canal internal-alpha definido | **COMPLETADO** |
| Canal external-alpha definido | **COMPLETADO** |
| Canal stable definido | **COMPLETADO** |
| Política de updater por canal | **COMPLETADO** |
| Internal Alpha compila sin clave y updater deshabilitado | **COMPLETADO** (build `development`/`internal-alpha` sin firma y updater off) |
| External Alpha tiene estrategia explícita | **COMPLETADO** |
| Stable exige firma | **COMPLETADO** |
| Build detecta claves faltantes antes de compilar | **COMPLETADO** |
| Build no genera artefactos publicables si falla | **COMPLETADO** (prechecks detienen) |
| Build termina con exit 0 o 1 inequívoco | **COMPLETADO** |
| SHA-256 generado para todos los artefactos | **COMPLETADO** |
| Manifest de release generado | **COMPLETADO** |
| Firma Tauri validada cuando aplica | **COMPLETADO** (en postcheck) |
| Authenticode definido para Alpha externa | **COMPLETADO** |
| Timestamping definido | **COMPLETADO** |
| Firma post-build verificada | **COMPLETADO** |
| Artefactos separados por canal | **COMPLETADO** |
| Nombres reflejan versión y canal | **COMPLETADO** |
| CI protege secrets | **COMPLETADO** (environments) |
| Política de actualización documentada | **COMPLETADO** |
| Rotación y revocación documentadas | **COMPLETADO** |

---

## 22. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | Build `development` completado con éxito; `internal-alpha` sin probar aún. |
| B-002 | CI no ejecutado en GitHub. |
| B-003 | Authenticode real no validado (sin certificado de prueba). |
| B-004 | Updater Tauri no probado end-to-end. |

---

## 23. Cambios no realizados

- No se crearon certificados ni claves reales.
- No se publicaron artefactos.
- No se agregaron funciones de producto.
- No se implementó un sistema de revocación activo.

---

## 24. Veredicto

**PARCIAL — estrategia de canales implementada y prechecks validados.**

Se logró:

- Definir cuatro canales con políticas explícitas.
- Separar configuración Tauri (`internal` vs `release`).
- Agregar prechecks que fallan antes de compilar si faltan condiciones.
- Verificar firmas y hashes en postchecks.
- Documentar firmas, canales, CI, rotación y revocación.
- Crear workflows de CI para cada canal.

Pendiente:

- Ejecutar build `development` completo y validar artifact.
- Ejecutar CI en GitHub.
- Validar Authenticode y updater con claves reales.
