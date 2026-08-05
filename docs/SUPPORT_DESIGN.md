# Sentinel Support and Diagnostics Design

## Taxonomía de errores

| Categoría | Código base | Ejemplos |
| --------- | ----------- | -------- |
| Autenticación | `SEN-AUTH-###` | token inválido, sesión expirada |
| Sidecar | `SEN-SIDECAR-###` | sidecar no responde, port ocupado |
| Modelo | `SEN-MODEL-###` | modelo no disponible, timeout |
| Proveedor | `SEN-PROVIDER-###` | timeout, rate limit, 500 |
| Red | `SEN-NETWORK-###` | offline, DNS, proxy |
| Permiso | `SEN-PERMISSION-###` | recurso no permitido, grant denegado |
| Filesystem | `SEN-FS-###` | no encontrado, bloqueado, TOCTOU |
| Recurso cambiado | `SEN-RESOURCE-###` | archivo modificado después de grant |
| Ejecución | `SEN-EXEC-###` | tool falló, efecto parcial |
| Verificación | `SEN-VERIFY-###` | verificación pendiente, fallo |
| Auditoría | `SEN-AUDIT-###` | auditoría falló, sin evidencia |
| Persistencia | `SEN-PERSIST-###` | DB corrupta, write falló |
| Configuración | `SEN-CONFIG-###` | JSON inválido, schema antiguo |
| Instalación | `SEN-INSTALL-###` | faltan archivos, sidecar ausente |
| Actualización | `SEN-UPDATE-###` | updater offline, firma inválida |
| Desconocido | `SEN-UNKNOWN-###` | cualquier otro con correlation ID |

## Contrato de mensaje

Todo mensaje de error para usuario debe contener:

1. Título breve.
2. Qué ocurrió.
3. Qué no ocurrió, si es relevante.
4. Acción recomendada.
5. Código de soporte.
6. Botón de acción (reintentar, configuración, diagnóstico, cancelar).

## Redacción

- Modo usuario: lenguaje sencillo, sin stack traces, sin nombres de clases, sin HTTP crudo.
- Modo desarrollador: detalles técnicos plegados, con correlation ID, IDs y hashes.
- Diagnóstico exportado: estructurado, redactado, con checksum.

## Patrones de redacción central

- `Authorization: Bearer <token>` -> `Authorization: Bearer [REDACTED]`
- `api_key`, `secret`, `password`, `token`, `client_secret`, `private_key`
- `sk-...` keys
- Rutas `C:\Users\<nombre>` -> `C:\Users\[REDACTED]`
- No redactar correlation IDs, códigos de error, versiones, hashes, estados.

## Build ID visible

Debe mostrarse en:

- Settings > Acerca de
- Diagnóstico
- Logs

Formato:

```text
Sentinel 0.1.0-alpha.1
Build: internal-alpha-20260804-9bdfe7e
Commit: 5c03e8b
Canal: internal-alpha
```

## Correlation ID

Cada flujo importante genera un ID corto de soporte. Debe enlazar GUI -> Tauri -> sidecar -> planner -> execution -> audit.

## Contenido mínimo del diagnóstico

```text
summary.json:
  product_version
  build_id
  channel
  commit
  timestamp
  windows_version
  language
  sidecar_status
  sidecar_version
  sidecar_hash
  model_status
  provider_status
  cloud_authority
  recent_error_codes
  disk_space
  memory_snapshot

logs/ redacted
system.txt
manifest.json
README.txt
```

## Niveles de restablecimiento

1. **Interfaz**: layout y preferencias visuales; no toca datos.
2. **Configuración**: settings, permisos; conserva historial y vault.
3. **Completo**: requiere confirmación fuerte, lista de elementos a eliminar, backup opcional.

## Logs estructurados

Cada línea debe incluir:

```text
timestamp
level
component
event
error_code
correlation_id
message
build_id
```

No serializar objetos completos con secretos.
