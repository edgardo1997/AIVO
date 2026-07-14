# Fase 3: Context Engine + Memory - Cierre

## Objetivo
El sistema puede entender su propio estado (ContextEngine) y recordar informacion a traves del tiempo (Memory).

## Archivos creados

### sentinel/core/context.py
- SystemContext: dataclass con cpu, memory, disk, network, processes, boot_time, timestamp
  - 	o_dict(): serializacion completa
  - summary(): resumen ligero para politicas y decision engine
- ContextEngine:
  - collect(include_processes): recolecta estado completo del sistema en paralelo (cada sub-coleccion con try/except individual)
  - get_last_context(): acceso al ultimo contexto recolectado
  - Coleccion por categorias:
    - CPU: percent, per-core, frecuencia, load avg, conteo fisico/logico
    - RAM: virtual + swap (total, used, percent)
    - Disco: todas las particiones con uso + IO counters
    - Red: bytes/packets sent/recv + hasta 50 conexiones activas
    - Procesos: top N por CPU con PID, name, CPU%, mem%, RSS MB, status, create_time

### sentinel/core/memory.py
- Memory con persistencia SQLite:
  - KV Store: set/get/delete/list con serializacion JSON
  - Snapshots: guardar/recovery de contextos completos con timestamp
  - Sessions: crear/actualizar sesiones con datos arbitrarios
  - cleanup_old_snapshots(keep): rotacion automatica
  - Thread-safe con lock + conexion por hilo (threading.local)
  - WAL mode para concurrentcia

### Integraciones
- ToolGateway acepta context_engine opcional en constructor + set_context_engine()
- execute() enriquece automaticamente el contexto con system y system_summary si hay ContextEngine disponible
- core/__init__.py y sentinel/__init__.py actualizados con nuevos exports

## Prueba de aceptacion superada
- ContextEngine: CPU 9.4% | 8 cores, RAM 81.3%, Disk C: 15.7%, 117 conexiones, 5 procesos (limit=5)
- Memory: KV store read/write/delete, 2 snapshots con recovery, sessions con update, cleanup rotacional
- Gateway: tool ejecuta con contexto automatico enriquecido (500ms, success)
- 8/8 subtests pasan

## No se modifico
- sidecar/ intacto
- src/ intacto
- src-tauri/ intacto
- Ningun runtime, DB, log o proceso activo

## Proxima fase
Fase 4: Intent Engine + Model Router
- IntentEngine: parsea intencion en lenguaje natural a estructura accion/objetivo/parametros
- ModelRouter: selecciona modelo IA segun tipo de tarea
- Primer integracion: intent -> policy check -> tool execution
