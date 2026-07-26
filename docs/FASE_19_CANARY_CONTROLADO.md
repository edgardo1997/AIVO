# Fase 19 — Canary controlado

## Estado seguro inicial

- `CONTROLLED_RUNTIME_ACTIVATION_ENABLED=False`
- `V2_CANARY_ENABLED=False`
- `V2_TRAFFIC_PERCENTAGE=0`
- máximo configurable: `5%`
- kill switch independiente: activado por defecto

## Routing

La selección usa un bucket SHA-256 estable del `request_id`. Solamente los
buckets asignados al porcentaje configurado pueden llegar a V2. La decisión y
su identificador son deterministas e idempotentes.

Antes de seleccionar V2 se exige:

- elegibilidad canary;
- readiness aprobado;
- safety saludable;
- rollback disponible;
- scope explícitamente permitido;
- trial vigente;
- cero divergencias críticas.

## Exactly once y fallback

El coordinador conserva un resultado por `request_id`. Una repetición devuelve
el resultado existente sin llamar nuevamente a V2 ni a Legacy.

El fallback automático hacia Legacy solo ocurre antes de una ejecución V2:

- kill switch activo;
- precondición de routing fallida;
- policy/grant/Gateway o hashes inválidos;
- preflight V2 bloqueado antes del backend.

Después de que el backend V2 ha sido invocado, un fallo o timeout genera receipt
y diagnóstico, pero nunca una segunda ejecución automática en Legacy.

## Autoridad

La activación sigue desconectada del Orchestrator y del Runtime productivo.
Legacy continúa siendo el valor por defecto y el handler de fallback debe
inyectarse explícitamente durante una futura integración controlada.
