# Sentinel UX Design — Modo Usuario y Modo Desarrollador

## Principio

Sentinel oculte complejidad técnica sin ocultar control. El usuario normal debe ver lo necesario para decidir; el desarrollador puede ver cómo lo hizo.

## Modo Usuario (predeterminado)

### Navegación visible

- **Chat** — conversación principal.
- **Panel** — resumen del sistema.
- **Permisos** — autorizaciones activas.
- **Auditoría** — registro de acciones.
- **Ayuda** — documentación y soporte.

### Oculto en modo usuario

- Modelos, proveedores, métricas, consola, observabilidad, flota, agentes, plugins, disparadores, políticas YAML, perfil de usuario, reportes, vault (a menos que esté bajo Permisos).

### Lenguaje

- Provider → Servicio de IA
- Execution Grant → Permiso temporal
- Tool → Acción
- Pipeline → Proceso
- Clarification → Necesito más información
- Continuation → Solicitud pendiente
- Verification → Comprobación
- CloudAuthority → Permiso para usar cloud

## Modo Desarrollador

Se activa desde **Configuración > Interfaz** o con `Ctrl+Shift+D`.

Muestra:

- Centro de modelos
- Consola y observabilidad
- Agentes, plugins, flota, disparadores
- Auditoría técnica detallada
- Logs y diagnósticos

### Regla

El modo desarrollador es más detalle, no más autoridad. No puede saltar permisos, deshabilitar auditoría ni acceder a secretos.

## Onboarding Alpha

Cuatro decisiones esenciales:

1. ¿Usar IA local?
2. ¿Permitir cloud cuando no haya local?
3. ¿Qué carpetas puede usar Sentinel?
4. Confirmar y empezar.

No se piden: provider exacto, modelo, temperatura, tokens, retry strategy, context budget, tool registry.

## Defaults seguros

- Modo usuario = activo
- Cloud = no autorizado
- IA local = preferida
- Permisos = mínimos
- Carpetas = selección explícita
- Developer mode = deshabilitado

## Consentimiento

Siempre muestra:

- qué acción;
- qué recurso;
- dónde;
- riesgo;
- si es reversible;
- botones Aprobar/Rechazar;
- detalles técnicos plegados.

## Errores

Estructura obligatoria:

1. Qué ocurrió.
2. Qué no ocurrió.
3. Qué puede hacer el usuario.

No mostrar: stack trace, nombre de excepción, JSON crudo, códigos HTTP, rutas Python, schema Pydantic.

## Accesibilidad

- Foco visible y orden lógico.
- Tab navega todos los controles esenciales.
- Modales capturan foco y se cierran con Escape.
- Estados dinámicos anunciados visualmente.

## Telemetría

Para Alpha: observación manual. Si se agrega telemetría en el futuro: consentimiento, anonimización, desactivable, sin conversaciones ni secretos.
