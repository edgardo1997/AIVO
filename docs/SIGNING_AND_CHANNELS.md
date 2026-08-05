# Sentinel Signing and Channels

This document defines the canonical distribution channels, signing policies and artifact identity strategy.

## Channels

| Canal | Working tree | Updater | Firma Tauri | Authenticode | Hashes | Uso |
| ----- | ------------ | ------- | ----------- | ------------ | ------ | --- |
| `development` | dirty permitido | off | no | no | sí | desarrollador local |
| `internal-alpha` | limpio recomendado | off | no | no | sí | testers internos |
| `external-alpha` | limpio obligatorio | on | sí | requerido | sí | distribución cerrada |
| `stable` | limpio + tag | on | sí | requerido | sí | público |

## Política de canales

### development

- No se requiere `TAURI_SIGNING_PRIVATE_KEY`.
- No se requiere certificado Authenticode.
- Se permite `-AllowDirty`.
- El updater está deshabilitado.

### internal-alpha

- Working tree limpio o `-AllowDirty` para pruebas de integración.
- No se requiere `TAURI_SIGNING_PRIVATE_KEY`.
- No se requiere Authenticode.
- El updater está deshabilitado (`endpoints: []`).
- Hashes obligatorios.
- Manifest obligatorio.

### external-alpha

- Working tree limpio obligatorio.
- Se requiere `TAURI_SIGNING_PRIVATE_KEY`.
- Se requiere Authenticode.
- Se requiere timestamping.
- Updater habilitado (`tauri.release.conf.json`).
- Hashes publicados.

### stable

- Working tree limpio + tag en `HEAD`.
- Firma Tauri obligatoria.
- Authenticode obligatorio.
- Timestamping obligatorio.
- Updater habilitado.
- CI obligatorio.

## Firma Tauri Updater

Garantiza que el binario de actualización descargado por Sentinel es auténtico.

Requiere:

```text
TAURI_SIGNING_PRIVATE_KEY
TAURI_SIGNING_PRIVATE_KEY_PASSWORD (si la clave está cifrada)
```

La clave privada nunca se versiona. Debe vivir en un gestor de secretos (GitHub environment, Azure Key Vault, etc.).

La clave pública está embebida en `tauri.release.conf.json` y `src-tauri/src/lib.rs`.

## Authenticode

Identifica al publicador ante Windows.

Aplica a:

- `sentinel.exe`
- `sidecar.exe`
- instalador MSI/NSIS

Variables requeridas para `external-alpha` y `stable`:

```text
SENTINEL_AUTHENTICODE_THUMBPRINT
SENTINEL_TIMESTAMP_URL
```

Orden recomendado:

1. Build `sidecar.exe`
2. Firmar `sidecar.exe`
3. Build Tauri
4. Firmar `sentinel.exe`
5. Firmar instaladores

## Timestamping

Servidor RFC 3161. Ejemplo: `http://timestamp.digicert.com`.

Si falla el timestamp en canales que lo requieren, el build falla.

## Hashes

SHA-256 de todos los artefactos. Generados en `artifacts/<channel>/SHA256SUMS.txt`.

## Manifest

`artifacts/<channel>/manifest.json` incluye:

- product, version, channel
- commit, build_id, timestamp
- `updater_enabled`, `tauri_signed`, `authenticode`
- lista de artefactos con `sha256` y `size`

## Build por canal

### development

```powershell
.\scripts\build-alpha.ps1 -Channel development -AllowDirty
```

### internal-alpha

```powershell
.\scripts\build-alpha.ps1 -Channel internal-alpha
```

### external-alpha

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = "..."
$env:SENTINEL_AUTHENTICODE_THUMBPRINT = "..."
$env:SENTINEL_TIMESTAMP_URL = "..."
.\scripts\build-alpha.ps1 -Channel external-alpha
```

### stable

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = "..."
$env:SENTINEL_AUTHENTICODE_THUMBPRINT = "..."
$env:SENTINEL_TIMESTAMP_URL = "..."
.\scripts\build-alpha.ps1 -Channel stable
```

## CI/CD

- `.github/workflows/build-internal-alpha.yml` canal `internal-alpha`.
- `.github/workflows/build-external-alpha.yml` requiere environment y secrets.
- `.github/workflows/release-stable.yml` requiere tag, approvals y secrets.

## Rotación y revocación

1. Si se filtra la clave privada del updater: generar par nuevo, actualizar `pubkey` en `tauri.release.conf.json` y `src-tauri/src/lib.rs`, publicar nueva release.
2. Si se revoca el certificado Authenticode: publicar build con certificado nuevo, documentar thumbprint.
3. Para bloquear un build: publicar manifest con `revoked: true` y hash, retirar artefactos.

## Referencias

- `docs/BUILD_AND_RELEASE.md`: pipeline técnico.
- `scripts/build-alpha.ps1`: implementación de prechecks y postchecks.
