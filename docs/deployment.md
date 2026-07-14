# Lanzamiento y operación de Sentinel 1.0

## Plataforma soportada

Sentinel 1.0 se distribuye oficialmente para Windows x86-64 mediante Tauri. Los paquetes macOS/Linux quedan fuera de soporte hasta disponer de sidecars nativos, firma y pruebas de instalación propias.

## Configuración obligatoria

- El sidecar escucha exclusivamente en `127.0.0.1`.
- Tauri genera `SENTINEL_SESSION_TOKEN` en cada inicio.
- Configura `SENTINEL_USER_PASSWORD` si habilitas login JWT.
- Configura `SENTINEL_JWT_SECRET` explícitamente o deriva la firma de una sesión segura.
- Guarda la llave del vault fuera de la base mediante `SENTINEL_VAULT_KEY_FILE`.
- Conserva permisos en `confirm` y define reglas granulares antes de automatizar escrituras.
- `SENTINEL_MAX_REQUEST_BYTES` limita cuerpos HTTP (10 MiB por defecto).
- `SENTINEL_ENABLE_API_DOCS=1` habilita OpenAPI sólo para diagnóstico local; está apagado por defecto.
- Los plugins externos se ejecutan en procesos aislados. `SENTINEL_PLUGIN_TIMEOUT_SECONDS`, `SENTINEL_PLUGIN_MEMORY_MB` y `SENTINEL_PLUGIN_CPU_SECONDS` ajustan sus cuotas (5 s, 128 MiB y 5 s de CPU por defecto).
- El sandbox deniega red, subprocess, registro de Windows y archivos fuera del directorio del plugin. El IPC admite exclusivamente JSON limitado a 256 KiB de entrada y 1 MiB de salida.

Los JWT viven únicamente en memoria del WebView: no se guardan credenciales bearer en `localStorage` ni `sessionStorage`.

## ACL de Windows

En cada arranque de producción, Sentinel retira herencia y accesos amplios de sus directorios de datos, configuración, políticas, logs y staging de actualizaciones. Sólo el SID del usuario actual y `NT AUTHORITY\\SYSTEM` reciben control total. La base SQLite, sus archivos WAL/SHM y la llave del vault se protegen nuevamente al crearse o rotarse.

La aplicación falla de forma cerrada si Windows no puede aplicar una ACL requerida. `AIVO_TESTING=1` desactiva esta mutación exclusivamente en pruebas automatizadas. No copies manualmente secretos a un directorio externo sin aplicar una política equivalente.

No expongas el puerto 8765 mediante proxy, Docker `-p`, túneles o interfaces de red. Sentinel es una plataforma local.

## Proceso de release

1. Actualiza la versión en `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` y `/api/info`.
2. Ejecuta `npm run test:e2e`, `npm test -- --run`, `npm run build` y `cargo test`.
3. Construye el sidecar y ejecuta `scripts/smoke-release.ps1`.
4. Crea el tag `vX.Y.Z`.
5. GitHub Actions valida versiones, ejecuta todas las pruebas, firma los artefactos y crea un release borrador.
6. Verifica instalador, desinstalación, actualización y checksums antes de publicar el borrador.

## Firma de distribución

La clave privada del updater se guarda fuera del repositorio en `%LOCALAPPDATA%\Sentinel\signing\updater.key`, cifrada por Tauri con una contraseña aleatoria. La contraseña se conserva mediante DPAPI `CurrentUser`; ambos archivos tienen ACL exclusiva para el usuario y `SYSTEM`. Conserva una copia offline cifrada: perder esta clave impide actualizar instalaciones existentes.

El pipeline exige cuatro secretos antes de publicar: `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, `WINDOWS_CERTIFICATE` y `WINDOWS_CERTIFICATE_PASSWORD`. El certificado debe ser Authenticode OV/EV o Azure Artifact Signing, contener la EKU Code Signing, una clave privada y estar vigente. La publicación falla si cualquier MSI/EXE carece de firma válida o si falta una firma `.sig` del updater.

Para una compilación local completamente firmada ejecuta `scripts/build-signed.ps1 -CertificateThumbprint <THUMBPRINT>`. Un certificado autofirmado sirve para pruebas internas, pero no establece identidad pública ni evita SmartScreen y no debe usarse para releases.

## Rollback

Conserva el instalador y manifiesto firmado de la versión anterior. Si una actualización falla, detén la publicación, restaura el release previo y conserva la base local; las migraciones nunca deben eliminar automáticamente datos del usuario.
# SBOM, integridad y procedencia

Cada release genera tres SBOM CycloneDX (`npm`, `Python` y `Rust`), un
`release-manifest.json` y `SHA256SUMS`. Los dos archivos de integridad se firman
con la misma clave privada protegida del actualizador. El workflow también crea
atestaciones Sigstore de procedencia SLSA y vincula cada SBOM a los instaladores.

Antes de distribuir un release descargado, verifique los hashes localmente:

```powershell
python scripts/release_metadata.py verify --manifest release-metadata/release-manifest.json
```

Verifique además que GitHub reconoce el binario como producido por este
repositorio y workflow:

```powershell
gh attestation verify .\Sentinel_1.0.0_x64-setup.exe --repo edgardo1997/AIVO
```

La publicación permanece en borrador si falta un SBOM, una firma, un hash, una
atestación o una firma Authenticode válida. Nunca publique artefactos que sólo
superen una de estas verificaciones.
