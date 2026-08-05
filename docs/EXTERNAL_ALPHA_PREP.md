# Sentinel External Alpha Preparation

## Propósito

Transformar una Closed Alpha validada en una Alpha pública limitada, firme, actualizable, revocable, documentada y soportable.

## Alcance

- Canal `external-alpha` separado de `stable`.
- Versionado pre-release coherente.
- Authenticode para `sentinel.exe`, `sidecar.exe` e instalador.
- Firma de updater Tauri con `TAURI_SIGNING_PRIVATE_KEY`.
- Manifest de actualización firmado y con hashes.
- Política de privacidad y términos de Alpha.
- Consentimientos separados.
- Crash reporting deshabilitado u opt-in.
- Documentación mínima, soporte básico, estado y problemas conocidos.
- Rollout gradual, rollback, revocación de builds.
- Release gates automatizados.

## Release Gates

```text
source verification
working tree clean
version check
lint
unit
contract
constitutional gates
integration
security
Rust build
frontend build
sidecar build
sidecar smoke
Tauri build
hash comparison
installer smoke
Authenticode
timestamp validation
updater signature validation
artifact manifest
remote verification
```

## Manifest de release

```json
{
  "version": "0.1.0-alpha.4",
  "channel": "external-alpha",
  "commit": "...",
  "build_id": "...",
  "timestamp_utc": "...",
  "installer": "...",
  "sha256": "...",
  "authenticode": "valid",
  "updater_signature": "valid",
  "sidecar_sha256": "...",
  "compatibility": {
    "windows": "11",
    "arch": "x64"
  }
}
```

## Rollout

| Etapa | Porcentaje | Duración mínima | Criterio de avance |
| ----- | ----------:| --------------- | ------------------ |
| 1     | 5%         | 24 h            | Sin P0/P1, métricas estables |
| 2     | 20%        | 24 h            | Sin P0/P1 |
| 3     | 50%        | 48 h            | Sin regresión |
| 4     | 100%       | resto           | Métricas de soporte controladas |

## Requisitos previos

- FASE 16 Closed Alpha con `GO`.
- Sin P0/P1 abiertos.
- Instalador oficial elegido y validado en entorno limpio.
- Flujos principales funcionan desde GUI.
- Lifecycle, persistencia, diagnóstico, soporte probados.
- Rollback y reinstalación probados.

## Decisiones

- `GO`
- `NO-GO`
- `BLOQUEADO`
- `PAUSADO`
- `EXTENDER PREPARACIÓN`

No `GO` sin firma válida, updater probado, rollback, revocación, políticas publicadas y P0/P1 cerrados.
