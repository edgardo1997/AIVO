# Build candidato — `internal-alpha-candidate-20260805-80d3f4c`

| Campo | Valor |
|-------|-------|
| Canal | `internal-alpha-candidate` |
| Build ID | `internal-alpha-candidate-20260805-80d3f4c` |
| Commit | `80d3f4c` |
| Rama | `feature/normal-user-experience` |
| dirty | `false` |
| Fecha | 2026-08-05 |
| Updater | deshabilitado |
| Firma | no |
| Estado | **REVOCADO ANTES DE VALIDACIÓN MANUAL** |

## Artefactos

```text
artifacts/internal-alpha-candidate/Sentinel_internal-alpha-candidate-20260805-80d3f4c_x64-setup.exe
artifacts/internal-alpha-candidate/manifest.json
artifacts/internal-alpha-candidate/sidecar.sha256
```

## Hashes

| Artefacto | SHA-256 |
|-----------|---------|
| Instalador `Sentinel_0.1.0-alpha.1_x64-setup.exe` | `c8ee9d7f72a0db34e3a27ee5a7dce73910c49a2e675ff46fdfa69ecea5f75997` |
| Sidecar `sidecar.exe` | `3a5ad6e0516354594d37355bf14aa27abd36a069d5f226db74c0610d27dfdca8` |

## Resumen de gates verificados

- [x] `npm run build` ✅
- [x] `npm test` ✅ (154 passed)
- [x] `python -m pytest tests/test_auth_authorization.py` ✅ (53 passed)
- [x] `python -m pytest tests/test_local_profile.py` ✅ (9 passed)
- [x] `python -m pytest tests/test_account_linking.py` ✅ (7 passed)
- [x] `cargo test --locked --manifest-path src-tauri/Cargo.toml` ✅
- [x] `cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings` ✅
- [x] `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` ✅
- [x] Sidecar build + smoke ✅
- [x] Tauri bundle NSIS ✅
- [x] Working tree clean ✅

## Bloqueos externos

- Google y Microsoft requieren `client_id`, `redirect_uri` registrada y configuración real.
- No se realiza release pública.
- No se firma.
- Updater deshabilitado.

## Checklist de validación manual

```text
[ ] Instalar en máquina limpia.
[ ] Ejecutar Welcome.
[ ] Crear cuenta local con nombre.
[ ] Completar onboarding de 4 pasos.
[ ] Llegar a Home.
[ ] Ver nombre, estado, IA, cloud, permisos.
[ ] Abrir Configuración.
[ ] Abrir Soporte y Diagnóstico.
[ ] Activar y desactivar Modo Desarrollador.
[ ] Cerrar sesión.
[ ] Reabrir Sentinel.
[ ] Verificar que sesión y onboarding persisten.
[ ] Confirmar que Google y Microsoft muestran "Disponible próximamente".
[ ] Confirmar que no crean sesiones.
[ ] Confirmar que no autorizan cloud.
[ ] Confirmar que no conectan integraciones.
```

## Motivo de revocación

Candidato generado antes de completar los gates de seguridad de OAuth:

- `consume_state` no demostrado atómico.
- Sin rate limiting en endpoints OAuth.
- Sin ownership de transacciones.
- Sin invalidación al reinicio.
- Pruebas de loopback incompletas.
- Protección de PKCE verifier no verificada.

Se conservan los hashes como evidencia.

## Notas

Este build no reemplaza `internal-alpha-20260805-229cf37` (Fase 14). Era un candidato interno prematuro para validar el nuevo flujo de usuario normal.
