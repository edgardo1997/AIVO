# Taxonomía de Eventos y Errores — Sentinel

**Versión:** 0.1.0  
**Estado:** IMPLEMENTADO — en expansión gradual  

---

## 1. Esquema de evento estructurado

Todo evento estructurado de Sentinel debe incluir los siguientes campos.

### Obligatorios

```json
{
  "timestamp": "2026-08-05T18:00:00.000Z",
  "level": "INFO",
  "event_code": "SEN-AUTH-001",
  "message": "Sesión local iniciada",
  "build_id": "internal-alpha-20260805-...",
  "component": "session"
}
```

### Obligatorios cuando existe operación

```json
{
  "correlation_id": "uuid",
  "operation": "tool_execution",
  "status": "started"
}
```

### Opcionales

```json
{
  "request_id": "uuid",
  "session_id_hash": "sha256",
  "user_id_hash": "sha256",
  "duration_ms": 120,
  "provider": "google",
  "model": "qwen3",
  "tool": "filesystem.read",
  "error_code": null,
  "safe_context": {}
}
```

### Campos prohibidos

```text
api_key, access_token, refresh_token, id_token, authorization, bearer,
cookie, password, private_key, client_secret, code_verifier, authorization_code,
state, nonce, vault_secret, file_content, conversation, chain_of_thought
```

---

## 2. Prefijos y familias

| Prefijo | Componente |
|---------|------------|
| `SEN-AUTH` | Autenticación y sesión |
| `SEN-SESSION` | Gestión de sesión y lifecycle |
| `SEN-ONBOARD` | Onboarding y primer uso |
| `SEN-POLICY` | PolicyEngine y reglas |
| `SEN-GRANT` | Execution grants y consentimiento |
| `SEN-EXEC` | ExecutionPipeline y ejecución |
| `SEN-TOOL` | ToolGateway y herramientas |
| `SEN-STORAGE` | Persistencia, SQLite, vault |
| `SEN-OAUTH` | Proveedores OAuth y loopback |
| `SEN-SIDECAR` | Sidecar lifecycle y health |
| `SEN-BUILD` | Build info y versiones |
| `SEN-SUPPORT` | Diagnóstico, reparación, reset |
| `SEN-ACL` | Permisos y roles |
| `SEN-AI` | ModelRouter, proveedores, presupuesto |
| `SEN-NET` | Red y conectividad |
| `SEN-INT` | Integraciones externas |

---

## 3. Códigos iniciales

| Código | Significado | Severidad | Componente | Acción recomendada | Exposición al usuario |
|--------|-------------|-----------|------------|--------------------|-----------------------|
| `SEN-AUTH-001` | Sesión local iniciada | INFO | session | — | "Sesión lista" |
| `SEN-AUTH-002` | Sesión expirada | WARNING | session | Reautenticar | "Tu sesión expiró" |
| `SEN-AUTH-003` | Token inválido | WARNING | session | Reintentar login | "No se pudo validar la sesión" |
| `SEN-AUTH-004` | Rate limit de autenticación | WARNING | rate_limit | Esperar | "Demasiados intentos. Espera un momento" |
| `SEN-SESSION-001` | Perfil local creado | INFO | local_profile | — | "Perfil creado" |
| `SEN-ONBOARD-001` | Paso de onboarding guardado | INFO | onboarding | — | "Progreso guardado" |
| `SEN-ONBOARD-002` | Onboarding completado | INFO | onboarding | — | "Onboarding completo" |
| `SEN-POLICY-001` | Acción denegada por política | WARNING | policy | Revisar permisos | "Esta acción no está permitida" |
| `SEN-GRANT-001` | Grant creado | INFO | grant | — | "Esperando confirmación" |
| `SEN-EXEC-001` | Ejecución iniciada | INFO | execution | — | "Ejecutando..." |
| `SEN-EXEC-002` | Ejecución completada | INFO | execution | — | "Listo" |
| `SEN-EXEC-003` | Ejecución fallida | ERROR | execution | Revisar logs | "No se pudo completar la acción" |
| `SEN-TOOL-001` | Herramienta invocada | INFO | tool | — | — |
| `SEN-TOOL-002` | Herramienta denegada por guardián | WARNING | tool_guard | Revisar permisos | "Sentinel bloqueó esta acción" |
| `SEN-STORAGE-001` | Error de persistencia | ERROR | storage | Revisar disco/permisos | "No se pudo guardar el dato" |
| `SEN-OAUTH-001` | Transacción OAuth creada | INFO | oauth | — | "Iniciando autenticación" |
| `SEN-OAUTH-002` | Estado OAuth consumido | INFO | oauth | — | — |
| `SEN-OAUTH-003` | Replay de estado OAuth rechazado | WARNING | oauth | Ignorar | — |
| `SEN-SIDECAR-001` | Sidecar iniciado | INFO | sidecar | — | — |
| `SEN-SIDECAR-002` | Sidecar listo | INFO | sidecar | — | "Sentinel listo" |
| `SEN-SIDECAR-003` | Sidecar cerrado | INFO | sidecar | — | — |
| `SEN-SIDECAR-004` | Sidecar reiniciando | WARNING | sidecar | — | "Reiniciando motor" |
| `SEN-BUILD-001` | Build info cargada | INFO | build | — | — |
| `SEN-SUPPORT-001` | Paquete de diagnóstico creado | INFO | support | — | "Diagnóstico generado" |
| `SEN-SUPPORT-002` | Diagnóstico no pudo crearse | ERROR | support | Revisar logs | "No se pudo generar el diagnóstico" |
| `SEN-ACL-001` | Intento de escalación de rol rechazado | WARNING | auth | Auditar | "No tienes permiso para esto" |
| `SEN-AI-001` | Proveedor local seleccionado | INFO | ai | — | "Usando modelo local" |
| `SEN-AI-002` | Fallback a proveedor remoto | WARNING | ai | — | "Usando proveedor en la nube" |
| `SEN-NET-001` | Error de red | WARNING | network | Revisar conexión | "Problema de conexión" |
| `SEN-INT-001` | Configuración de integración requerida | INFO | integrations | Configurar proveedor | "Esta integración requiere configuración" |

---

## 4. Reglas de asignación

1. Un mismo fallo no debe tener códigos distintos en cada capa.
2. Cada nuevo código debe documentarse en esta tabla.
3. No reutilizar códigos legacy no documentados.
4. La severidad es informativa por defecto; aumentar solo con justificación.
5. El `message` es para operadores y usuarios; no incluir trazas técnicas.
6. Los detalles técnicos van en `safe_context` redactado.

---

## 5. Separación de responsabilidades

| Tipo | Propósito | Audiencia | Persistencia |
|------|-----------|-----------|--------------|
| **Log técnico** | Diagnóstico y trazabilidad | Operadores / soporte | `~/.sentinel/logs/*.jsonl` |
| **Auditoría** | Verdad operacional, grants, consentimiento | Sistema / governance | SQLite `audit_log` |
| **Mensaje de usuario** | Explicar qué ocurrió y qué hacer | Usuario final | No persistir |

No usar el mismo texto para los tres.

---

## 6. Expansión

A medida que se migren rutas legacy, se agregarán filas a la tabla de códigos. La migración global se considerará `PARCIAL` mientras existan logs no estructurados.
