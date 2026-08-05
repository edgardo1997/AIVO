# Sentinel Internal Alpha Program

## Propósito

Ejecutar una Alpha interna controlada con un grupo pequeño de usuarios técnicos para validar instalación, uso diario, actualización y diagnóstico fuera del entorno de desarrollo.

## Alcance

- Instalación con instalador oficial NSIS.
- Uso diario durante 7 días naturales.
- 5–10 instalaciones.
- Flujos principales A-F.
- Reporte estructurado de bugs.
- Correcciones P0/P1 con regresión.
- Actualización o reinstalación entre builds.

## Feature Freeze

Solo se aceptan:

- bugs;
- vulnerabilidades;
- bloqueos;
- instalación;
- rendimiento;
- estabilidad;
- UX que impida flujos;
- diagnóstico.

No se aceptan proveedores, tools, agentes, memorias, paneles, rediseños ni nuevas funciones.

## Build inicial

```text
Sentinel 0.1.0-alpha.1
Build ID: internal-alpha-20260804-9bdfe7e
Commit: 5c03e8b
Canal: internal-alpha
Updater: deshabilitado
```

## Registro de testers

| Tester ID | Device ID | Windows | CPU | RAM | Instalador | Build ID | Hash | Fecha |
| --------- | --------- | ------- | --- | ---:| ---------- | -------- | ---- | ----- |
| TESTER-01 | DEVICE-01 |         |     |     |            |          |      |       |
| TESTER-02 | DEVICE-02 |         |     |     |            |          |      |       |

## Flujos obligatorios

- A: primer inicio (instalar, abrir, onboarding, chat).
- B: conversación (enviar, streaming, cancelar, historial, reabrir).
- C: ambigüedad (solicitud ambigua, aclaración, replanning, consentimiento).
- D: demo PDF (buscar, Reviewed, copiar, abrir, auditoría).
- E: cloud (rechazar cloud, confirmar no se usó).
- F: settings (cambiar, cerrar, reabrir, persistencia).

## Plantilla de bug

```text
ID: ALPHA-XXX-###
Tester:
Device:
Build ID:
Versión:
Fecha:
Título:
Severidad: P0/P1/P2/P3/P4
Flujo:
Pasos:
Esperado:
Real:
Frecuencia:
Pérdida de datos:
Código de soporte:
Correlation ID:
Diagnóstico:
Estado:
```

## Plantilla de instalación

```text
Tester ID:
Device ID:
Windows:
Build:
CPU:
RAM:
Instalador:
Hash:
SmartScreen:
UAC:
Duración:
Primer inicio:
Onboarding:
Sidecar:
Errores:
Intervención técnica:
```

## Problemas conocidos

| ID | Síntoma | Build afectado | Workaround | Estado |
| -- | ------- | -------------- | ---------- | ------ |
|    |         |                |            |        |

## Métricas

```text
installation_success_rate
first_start_success_rate
session_success_rate
flow_completion_rate
crash_rate
P0_count
P1_count
diagnostic_success_rate
```

## Criterios de salida

- 5–10 instalaciones completadas.
- 7 días naturales de uso.
- Flujos principales completados.
- Sin P0.
- Sin P1.
- Bugs importantes reproducibles o instrumentados.
- Diagnóstico funcional.
- Actualización o reinstalación probada.

## Decisión

- `GO`
- `NO-GO`
- `EXTENDER ALPHA`

No declarar `GO` si existe P0, P1, menos de 5 instalaciones, builds no trazables, o la actualización/reinstalación falla.
