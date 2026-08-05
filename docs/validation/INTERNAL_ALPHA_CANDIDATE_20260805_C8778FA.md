# Build candidato — `internal-alpha-candidate-20260805-c8778fa`

| Campo | Valor |
|-------|-------|
| Canal | `internal-alpha-candidate` |
| Build ID | `internal-alpha-candidate-20260805-c8778fa` |
| Commit | `c8778fa` |
| Rama | `feature/normal-user-experience` |
| dirty | `false` |
| Fecha | 2026-08-05 |
| Updater | deshabilitado |
| Firma | no |
| Estado | **PENDIENTE VALIDACIÓN MANUAL** |

## Artefactos

```text
artifacts/internal-alpha-candidate/Sentinel_internal-alpha-candidate-20260805-c8778fa_x64-setup.exe
artifacts/internal-alpha-candidate/manifest.json
artifacts/internal-alpha-candidate/sidecar.sha256
```

## Hashes

| Artefacto | SHA-256 |
|-----------|---------|
| Instalador `Sentinel_internal-alpha-candidate-20260805-c8778fa_x64-setup.exe` | `86b7ad7e771071a89280f68b9ef88bff50b56b312899f542602caf3ded2394c0` |
| Sidecar `sidecar.exe` | `d8c4ada4898615470f612bc734f51289bc18dabec4697f2961c2a94815154a1f` |

## Resumen de gates verificados

- [x] `npm run build` ✅
- [x] `npm test` ✅ (154 passed)
- [x] `python -m pytest tests/test_auth_authorization.py` ✅ (53 passed)
- [x] `python -m pytest tests/test_local_profile.py` ✅
- [x] `python -m pytest tests/test_account_linking.py` ✅
- [x] `python -m pytest tests/test_oauth_loopback.py` ✅
- [x] `python -m pytest tests/test_oauth_atomic.py` ✅
- [x] `python -m pytest tests/test_oauth_verifier_security.py` ✅
- [x] `python -m pytest tests/test_oauth_endpoints_security.py` ✅
- [x] `python -m pytest tests/test_oauth_ownership.py` ✅
- [x] `python -m pytest tests/test_oauth_rate_limit.py` ✅
- [x] `python -m pytest tests/test_onboarding_security.py` ✅
- [x] `cargo test --locked --manifest-path src-tauri/Cargo.toml` ✅
- [x] `cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings` ✅
- [x] `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` ✅
- [x] Sidecar build + smoke ✅
- [x] Tauri bundle NSIS ✅
- [x] Working tree clean ✅

## Criterios de salida del bloque OAuth

- [x] `consume_state` atómico probado (UPDATE ... WHERE rowcount == 1)
- [x] Replay concurrente rechazado
- [x] Ownership aplicado en endpoints y repositorio
- [x] Rate limits probados (acción, usuario, proveedor, ventana)
- [x] Restart invalidation probada (verifier en memoria, transacciones expiradas)
- [x] Verifier no expuesto (0 coincidencias en SQLite, logs, JSON, diagnóstico)
- [x] Loopback suite completa verde (bind, puerto, path, duplicados, timeout, shutdown)
- [x] Endpoints negativos verdes (provider inválido, tx desconocida, cancel sin ownership)
- [x] Onboarding security verde (persistencia, paso inválido, cloud authority no concedida)
- [x] Frontend verde
- [x] Backend verde
- [x] Rust verde

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

## Notas

- Este build reemplaza al candidato `internal-alpha-candidate-20260805-80d3f4c`, que fue revocado antes de validación por gates de OAuth incompletos.
- Google y Microsoft requieren `client_id`, `redirect_uri` registrada y configuración real.
- No se realiza release pública.
- No se firma.
- Updater deshabilitado.
