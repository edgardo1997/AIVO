# Sentinel Closed Alpha Program

## Propósito

Validar que Sentinel puede ser instalado, comprendido y utilizado por personas no técnicas durante un periodo controlado.

## Alcance

- 20–50 usuarios no técnicos.
- Duración mínima: 14 días.
- Build con canal `closed-alpha`.
- Consentimiento explícito.
- Métricas de instalación, onboarding, tareas, consentimiento, soporte y desinstalación.

## Requisitos previos

- Alpha interna con `GO`.
- Sin P0 ni P1 abiertos.
- Instalador oficial y firmado.
- Build ID visible.
- Diagnóstico exportable.
- Restablecimiento probado.
- Rollback/reinstalación probados.
- Política de privacidad y telemetría.
- Canal de soporte.

## Consentimiento

- Naturaleza Alpha.
- Riesgos.
- Datos almacenados.
- Cloud.
- Diagnóstico.
- Telemetría (deshabilitada u opcional).
- Soporte.
- Revocación.

## Tareas principales

1. Conversación.
2. Historial persistente.
3. Cambiar settings.
4. Permitir carpetas.
5. Solicitud ambigua.
6. Demo PDF.
7. Revisar auditoría.
8. Crear diagnóstico.

## Métricas

- `installation_success_rate`
- `onboarding_completion_rate`
- `first_task_success_rate`
- `main_flow_completion_rate`
- `consent_comprehension_rate`
- `audit_findability_rate`
- `diagnostic_export_rate`
- `support_request_rate`
- `crash_rate`
- `uninstall_success_rate`

## Puntuación

| Área | Peso |
| ---- | ---:|
| Instalación | 15 |
| Onboarding | 10 |
| Tareas principales | 20 |
| Consentimiento | 15 |
| Seguridad y datos | 15 |
| UX | 10 |
| Soporte | 5 |
| Diagnóstico | 5 |
| Actualización/rollback | 5 |

## Decisiones

- `GO`
- `NO-GO`
- `EXTENDER ALPHA`
- `PAUSADA`
- `BLOQUEADA`

No `GO` si existen P0, P1, menos de 20 usuarios, pérdida de datos, ejecución no autorizada o soporte inviable.
