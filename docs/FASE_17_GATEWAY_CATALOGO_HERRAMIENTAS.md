# Fase 17 — Gateway y catálogo de herramientas

## Frontera implementada

El Gateway V2 pasivo ya no acepta una categoría amplia como identidad
suficiente. Cada evaluación requiere:

- `tool_id` estable y versión exacta;
- catálogo inmutable firmado con Ed25519;
- hash del catálogo y de cada especificación;
- schema cerrado de parámetros;
- scope permitido por la especificación;
- plan, paso, herramienta y hash de parámetros autorizados por el grant;
- evidencia, issuer y correlación válidos.

Las categorías anteriores permanecen como metadato de compatibilidad y deben
coincidir con la especificación firmada.

## Catálogo inicial

El artefacto incorporado está firmado fuera del flujo de ejecución y su clave
pública está fijada en el código. Contiene herramientas pasivas y verificables
para lectura, análisis, información de sistema, información de procesos y
cambios previamente aprobados.

No contiene comandos, ejecutables, rutas ni scripts. Los parámetros solamente
pueden ser booleanos, enteros acotados o valores enumerados declarados por la
especificación.

## Cierre de seguridad

La evaluación se bloquea ante:

- herramienta o versión ausente del catálogo;
- firma, hash de catálogo o hash de especificación inválidos;
- parámetro desconocido, peligroso, mal tipado o fuera de rango;
- hash de parámetros diferente;
- categoría o scope incompatible;
- plan, paso o herramienta diferentes del grant;
- grant consumido, expirado, revocado o manipulado;
- evidencia, issuer o correlación inconsistentes.

Cada resultado conserva en su auditoría contractual el `tool_id`, versión,
catálogo, plan, paso y hashes pertinentes. El Gateway sigue siendo pasivo:
`TOOL_ALLOWED` mantiene `authority=False` y `execution_requested=False`.

Legacy Runtime continúa siendo la única autoridad productiva.
