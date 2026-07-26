# Fase 16 — Autoridad y consentimiento únicos

## Autoridades

- `DecisionResultV1` expresa una recomendación y siempre conserva
  `authority=False` y `execution_requested=False`.
- `PolicyEvaluationResultV1` es la única decisión final de política dentro del
  pipeline V2 pasivo.
- `ConsentDecisionResultV1` registra evidencia humana explícita. No es una
  autorización operacional.
- `AuthorizationGrantV1` es la única autorización limitada derivada de una
  política compatible y un consentimiento concedido.

## Flujo cerrado

```text
Decision recommendation
  -> Policy evaluation
  -> Human consent evidence
  -> Limited authorization grant
  -> Passive gateway and validation stages
  -> Grant consumption
```

Un consentimiento concedido produce directamente la evaluación del grant. No
existe una segunda aprobación humana dentro de `AuthorizationManagerV2`.

## Invariantes

- El grant es temporal, de un solo uso y se vincula al plan, paso, herramienta,
  identidad, decisión de política y hash exacto de parámetros.
- Una política bloqueada o desconocida impide emitir el grant.
- Un consentimiento pendiente, rechazado, revocado o expirado impide emitirlo.
- El consumo compara el hash de parámetros en tiempo constante.
- Un grant consumido, expirado, revocado o modificado se rechaza.
- El Tool Gateway vuelve a comprobar el estado de consumo y el hash de
  parámetros antes de emitir una evaluación pasiva.
- Ninguna parte de esta fase ejecuta herramientas ni cambia la autoridad del
  Runtime Legacy.

## Estado de integración

La integración permanece pasiva. `AUTHORIZED_LIMITED` y `TOOL_ALLOWED` no
representan ejecución real: todos los contratos derivados conservan
`authority=False` y `execution_requested=False`.
