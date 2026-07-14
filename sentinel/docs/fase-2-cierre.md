# Fase 2: Policy Engine - Cierre

## Objetivo
Crear el sistema de politicas granulares que reemplaza el concepto de \"4 niveles\" por una evaluacion flexible, componible y auditable de permisos.

## Archivos creados

### sentinel/core/policy.py
- Enum PolicyEffect: ALLOW, DENY, REQUIRE_CONFIRM
- Dataclass PolicyResult: effect, policy_id, reason, context
- Clase abstracta Policy con policy_id(), description(), evaluate(tool_id, params, context)

### sentinel/core/policy_engine.py
- PolicyEngine con:
  - egister(policy, permissions): asocia una politica a uno o mas permisos
  - unregister(policy_id)
  - evaluate(tool_id, params, context, required_permissions): evalua todas las politicas aplicables
  - Logica de composicion: DENY > REQUIRE_CONFIRM > ALLOW
  - Default effect configurable (por seguridad: DENY por defecto)
  - Fail-closed: si no hay politicas registradas para un permiso, aplica default_effect

### sentinel/policies/ (nuevo directorio)
- security_policies.py:
  - PermissionLevelPolicy: mapea los 4 niveles (view/confirm/auto/admin) a efectos segun el tipo de tool
  - EmergencyStopPolicy: kill switch global, evalua primero, DENY si activo

### Integracion en ToolGateway
- Constructor acepta policy_engine opcional
- set_policy_engine(engine) para configurar post-creacion
- execute() evalua politicas antes de ejecutar la tool:
  - Si DENY -> ToolResult.fail con mensaje de la politica
  - Si REQUIRE_CONFIRM -> ToolResult.needs_confirm() con razon
  - Si ALLOW -> ejecuta normal

### ToolResult ampliado
- Nuevos campos: equires_confirmation (bool), policy_decision (str)
- Nuevo factory method: ToolResult.needs_confirm(reason, tool_id, policy_id)

## Prueba de aceptacion superada
- [confirm] system.info: ALLOW (lectura permitida en nivel confirm)
- [view] system.info: ALLOW (lectura permitida en nivel view)
- [emergency] system.info: DENY (emergency stop bloquea todo)
- [no_policy] system.info: ALLOW (gateway sin policy engine no evalua)
- [no_policy_registered] system.info: DENY (fail-closed por defecto)
- 5/5 tests pasan

## No se modifico
- sidecar/ intacto
- src/ intacto
- src-tauri/ intacto
- Ningun runtime, DB, log o proceso activo

## Proxima fase
Fase 3: Context Engine + Memory
- ContextEngine: recopilacion estructurada del estado del sistema
- Memory: almacenamiento persistente de contexto (SQLite + sesiones)
- Primer contexto completo: system state (CPU, RAM, disco, red, procesos)
- Integracion: pasar contexto a PolicyEngine y ToolGateway
