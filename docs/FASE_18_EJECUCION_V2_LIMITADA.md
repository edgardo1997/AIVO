# Fase 18 — Ejecución V2 limitada

## Alcance

Se añadió una frontera opt-in, apagada por defecto, capaz de ejecutar únicamente:

- consulta básica de información del sistema mediante APIs de Python;
- lectura de metadata mediante un `resource_id` resuelto por un catálogo interno;
- solicitud de apertura de una aplicación mediante un
  `ApplicationDescriptorV1` instalado y verificado.

No acepta borrado, instalación, terminación de procesos, comandos, argumentos,
scripts, rutas procedentes del usuario ni payloads ejecutables.

## Cadena obligatoria

```text
Policy
  -> consentimiento humano
  -> grant limitado
  -> catálogo firmado y Tool Gateway
  -> validación plan/paso/tool/params
  -> consumo único del grant
  -> backend limitado
  -> receipt
  -> auditoría y telemetría
```

Una modificación del correlation ID, evidence hash, plan, paso, herramienta,
parámetros, descriptor o estado del grant cierra la operación antes del backend.

## Receipts y recuperación

Todas las solicitudes producen `LimitedExecutionReceiptV1`. Las aperturas
aceptadas producen además `LaunchReceiptV1` con estado `launch_requested`; no se
afirma que exista ventana o proceso saludable sin evidencia posterior.

El timeout es lógico y acotado. Un fallo o timeout recomienda fallback, pero no
invoca automáticamente Legacy, evitando doble ejecución. El grant ya consumido
no puede reutilizarse.

## Activación

`LIMITED_EXECUTION_V2_ENABLED` permanece `False`. La capa no está conectada a UI,
Orchestrator ni Runtime Legacy. La activación futura debe inyectar explícitamente
el backend, el consumidor del grant, el catálogo de recursos y la telemetría.

Legacy Runtime continúa disponible y sigue siendo la autoridad productiva.
