# Sentinel Advisory & Confidence Layer

## Propósito y límite de autoridad

Esta capa observa una salida ya producida por el Orchestrator y comunica confianza, incertidumbre, riesgos, contradicciones y oportunidades. No decide, no modifica planes, no ejecuta herramientas, no concede permisos y nunca bloquea una operación. El usuario conserva la decisión final.

La integración es *fail-open*: una excepción interna del análisis se registra y la salida original continúa sin cambios. La capa puede desactivarse con `SENTINEL_ADVISORY_ENABLED=false`.

## Flujo

1. Decision Engine y Policy Engine conservan toda su autoridad actual.
2. El Orchestrator termina o simula la ejecución y crea `ExecutionResult`.
3. `AdvisoryService` recibe ese resultado como entrada de solo lectura.
4. `ConfidenceEngine` calcula una estimación heurística explicable. No es una probabilidad matemática.
5. Las reglas producen observaciones y un nivel de intervención entre 0 y 3.
6. API serializa el informe separado en `advisory`.
7. La UI presenta una notificación flotante sólo si supera el umbral configurado.
8. Una acción del usuario genera una nueva intención para el Orchestrator; nunca altera automáticamente la ejecución anterior.

## Contratos

- `AdvisoryReport`: puntuación, etiqueta, explicación, factores positivos/negativos, observaciones, evidencia y acciones declarativas.
- `AdvisoryInsight`: tipo, título, detalle y nivel.
- `AdvisoryAction`: etiqueta y una intención delegable o acción puramente local.
- `AdvisoryService`: servicio reemplazable que acepta reglas adicionales sin importar el Orchestrator.

Los niveles son: 0 sin intervención, 1 sugerencia, 2 advertencia y 3 recomendación crítica. Ninguno representa un bloqueo.

## Configuración

- `SENTINEL_ADVISORY_ENABLED`: activa o desactiva la capa; predeterminado `true`.
- `SENTINEL_ADVISORY_THRESHOLD`: nivel mínimo de notificación, de 0 a 3; predeterminado `1`.
- `SENTINEL_ADVISORY_STALE_HOURS`: reservado para reglas de vigencia temporal; predeterminado `24`.

## Extensión segura

Las reglas inyectadas implementan `evaluate(result, confidence)` y devuelven observaciones. Deben ser deterministas y no poseer referencias al gateway, Policy Engine ni ejecutores. Una futura implementación multi-modelo puede generar observaciones adicionales detrás del mismo contrato, manteniendo las reglas deterministas como respaldo local.

## Decisiones arquitectónicas

Se eligió un postprocesador observable en vez de una nueva etapa de decisión. Esto evita autoridad duplicada, dependencias circulares y cambios implícitos del plan. `ExecutionResult.advisory` es metadato separado, por lo que consumidores antiguos siguen funcionando aunque ignoren el campo.
