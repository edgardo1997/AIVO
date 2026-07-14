# Fase 1: Tool Gateway + Adapter Interface - Cierre

## Objetivo
Crear la interfaz abstracta Tool y el ToolGateway como punto unico de registro y ejecucion de herramientas. Demostrar el patron con un adapter concreto (system).

## Archivos creados

### sentinel/core/tool.py
- Clase abstracta Tool con metodo spec() y execute(params, context)
- Dataclass ToolSpec: id, name, description, version, parameters (JSON Schema), required_permissions, timeout, status, category
- Dataclass ToolResult: success, data, error, tool_id, execution_id, duration_ms, timestamp
- Metodos de fabrica ToolResult.ok() y ToolResult.fail()

### sentinel/core/tool_gateway.py
- Clase ToolGateway con metodos:
  - egister(tool) / unregister(tool_id)
  - get_spec(tool_id) / list_specs() / list_active()
  - execute(tool_id, params, context) con timing, logging, y captura de errores

### sentinel/adapters/system_adapter.py
- SystemInfoTool: CPU, RAM, disco, red, uptime
- CpuInfoTool: por-core, frecuencia, load avg
- ProcessListTool: top N procesos por CPU con parametro limit

## Prueba de aceptacion superada
- 3 tools registradas y listadas
- system.info ejecuta correctamente (516ms)
- system.cpu ejecuta con 8 cores detectados (906ms)
- system.processes lista 5 procesos con limit=5
- Tool inexistente devuelve error controlado
- Errores de ejecucion capturados como ToolResult.fail (no excepcion)

## No se modifico
- sidecar/ intacto
- src/ intacto
- src-tauri/ intacto
- Ningun runtime, DB, log o proceso activo

## Proxima fase
Fase 2: Policy Engine
- Interfaz Policy abstracta
- PolicyEngine que evalua politicas contra contexto
- Migrar el concepto de \"4 niveles\" a politicas granulares
- Primera politica: system.read (permiso basico de lectura)
- Integracion con ToolGateway (verificar permisos antes de ejecutar)
