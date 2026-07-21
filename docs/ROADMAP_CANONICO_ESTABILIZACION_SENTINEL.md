# Sentinel — Roadmap canónico de estabilización

**Fecha de revisión:** 21 de julio de 2026  
**Estado del producto:** desarrollo interno; no autorizado para publicación general  
**Visión rectora:** Sentinel es una Trust Layer entre el usuario, las IA, las
herramientas y el sistema operativo.

## Propósito de este documento

El repositorio acumuló dos numeraciones diferentes para las fases 1 y 2. Este
roadmap conserva el trabajo real ya implementado, elimina la ambigüedad y ordena
únicamente lo que falta para obtener un producto estable. No introduce nuevas
capacidades grandes.

## Regla de estado

- **Aplicada:** existe implementación y evidencia focalizada.
- **Integrada:** convive correctamente con el producto completo.
- **Cerrada:** build, lint, regresión completa y criterios de seguridad pasan.

Una fase puede estar aplicada sin estar todavía integrada o cerrada.

## Asociación de las fases 0–4 existentes

### Fase 0 — Línea base y preservación

**Estado:** aplicada históricamente; revalidación necesaria.

Existe un snapshot recuperable, exclusión de datos runtime, búsqueda de secretos
y mitigación del watcher bajo OneDrive. Sin embargo, el árbol actual vuelve a
contener una cantidad elevada de cambios sin consolidar. La fase no se repite:
su garantía se recuperará en la Fase 5.

**Evidencia:** `docs/FASE_0_CIERRE_LINEA_BASE.md`.

### Fase 1 — Autoridad objetiva y Decision Engine seguro

**Estado:** aplicada; integración pendiente de una regresión global verde.

El modelo permanece como asesor sin autoridad. El riesgo, las políticas, los
permisos y la confirmación humana determinan la decisión. Las pruebas focalizadas
del Decision Engine pasan.

**Evidencia:** `docs/FASE_1_CIERRE_DECISION_ENGINE_SEGURO.md` y
`tests/test_decision_engine_seguro.py`.

### Fase 2 — Grounding integrado

**Estado:** aplicada; integración pendiente de una regresión global verde.

El plan exige evidencia real para consultas del sistema y reutiliza la ejecución
gobernada por ToolGateway. Una respuesta del modelo no se considera evidencia.

**Evidencia:** `docs/FASE_2_CIERRE_GROUNDING_INTEGRADO.md`.

### Fase 3 — Presentation Layer

**Estado:** aplicada e integrada en frontend; cierre global pendiente.

La presentación traduce el resultado del pipeline sin decidir ni ejecutar. El
frontend compila y sus 129 pruebas pasan, aunque queda una advertencia de lint.

**Evidencia:** `docs/FASE_3_CIERRE_PRESENTATION_LAYER.md`.

### Fase 4 — Reliable Memory

**Estado:** aplicada; cierre global pendiente.

La memoria operacional incorpora propietario, procedencia, confianza, vigencia y
borrado. Las pruebas focalizadas de memoria pasan. No concede permisos ni altera
el riesgo.

**Evidencia:** `docs/FASE_4_CIERRE_RELIABLE_MEMORY.md`.

## Resultado de la revalidación actual

- Frontend: 129 pruebas pasan y el build de producción termina correctamente.
- Rust/Tauri: 4 pruebas pasan; formato, test y check terminan correctamente.
- Python focalizado de fases 1–4: 84 pruebas pasan y 1 falla por una regresión de
  ModelRouter, no por Decision Engine, confirmaciones o memoria.
- Ruff falla por una variable sin uso en `model_router.py`.
- La regresión completa falla de forma amplia porque `ModelRouter` consulta
  `_task_type_map` sin inicializarlo.
- La matriz central de capacidades y el broker de confirmación existen, pero
  varias rutas mutables continúan llamando servicios directamente y no pasan por
  la matriz o ToolGateway.

Por ello, las fases 0–4 se conservan como trabajo aplicado, pero el producto no
puede considerarlas cerradas en conjunto hasta completar la consolidación.

# Fases restantes

## Fase 5 — Consolidación de integración

**Objetivo:** recuperar una única línea base verde sin añadir funciones.

### Trabajo

1. Inicializar y migrar correctamente toda la configuración de ModelRouter.
2. Eliminar el error Ruff y la advertencia frontend restante.
3. Corregir las regresiones derivadas del nuevo routing sin debilitar pruebas.
4. Ejecutar dos regresiones Python completas consecutivas.
5. Ejecutar frontend, Rust y pruebas de rendimiento.
6. Clasificar y retirar archivos temporales, duplicados y documentación obsoleta.
7. Consolidar el resultado en un commit recuperable.

### Gate

- Ruff limpio.
- Oxlint sin advertencias.
- Pytest completo dos veces sin fallos.
- Frontend build y tests verdes.
- Cargo fmt, test y check verdes.
- Worktree de la fase identificable y recuperable.

## Fase 6 — Frontera de confianza completa

**Objetivo:** impedir cualquier ejecución o mutación fuera del pipeline oficial.

### Trabajo

1. Inventariar todos los endpoints mutables.
2. Enrutar cada mutación por ToolGateway o una autorización central equivalente.
3. Aplicar la matriz viewer/user/admin a configuración, permisos, plugins, Fleet,
   Vault, auditoría y emergency stop.
4. Sustituir confirmaciones paralelas por un único broker.
5. Exigir vínculo de usuario, herramienta, parámetros, plan, riesgo, expiración y
   uso único.
6. Redactar secretos antes de persistir contexto o acciones pendientes.
7. Probar expiración, replay, cambio de usuario, manipulación y concurrencia.

### Gate

- Ningún endpoint mutable sin autorización explícita.
- Ningún bypass del flujo intención → plan → políticas → autorización → ejecución
  → auditoría.
- Matriz completa de roles pasando.
- Emergency stop falla cerrado.

## Fase 7 — Routing y conversación confiables

**Objetivo:** que el proveedor y modelo mostrados sean los que realmente responden.

### Trabajo

1. Usar una sola configuración persistente de routing.
2. Restaurar proveedor, modelo, estrategia y mapa por tipo de tarea al reiniciar.
3. Hacer al backend la única fuente de disponibilidad.
4. Validar clave, modelo, autenticación y cuota con health checks limitados.
5. Aplicar un presupuesto total de timeout y fallbacks clasificados.
6. Registrar proveedor, modelo, motivo, primer token, tokens y costo.
7. Mantener el token de sesión dentro de Rust.
8. Separar timeout de conexión, primer evento e inactividad del stream.

### Gate

- Reiniciar conserva proveedor y modelo.
- La metadata coincide con el proveedor que respondió.
- Claves inválidas y falta de cuota fallan rápidamente.
- Ninguna cadena de fallback tarda minutos.
- Conversaciones largas pueden cancelarse y conservar su respuesta parcial.

## Fase 8 — Runtime, persistencia, rendimiento y reversibilidad

**Objetivo:** mantener Sentinel estable durante sesiones largas y operaciones
reales.

### Trabajo

1. Sacar filesystem, procesos y comandos bloqueantes del event loop.
2. Corregir el benchmark de procesos y establecer presupuestos en CI.
3. Consolidar conexiones, PRAGMA y migraciones SQLite.
4. Usar una sola fuente protegida para conversaciones y memoria visible.
5. Reducir `localStorage` a una caché mínima sin contenido sensible.
6. Hacer backup, restore y rollback atómicos y auditados.
7. Definir límites de tamaño, profundidad, CPU, memoria, concurrencia y duración.
8. Usar relojes monotónicos para métricas de duración.

### Gate

- Health continúa respondiendo durante herramientas lentas.
- Benchmarks dentro del presupuesto.
- Reiniciar no pierde conversación ni configuración.
- Migración, backup y restore pasan bajo fallo inyectado y concurrencia.
- Toda modificación reversible demuestra rollback real.

## Fase 9 — Coherencia de producto y UX de confianza

**Objetivo:** presentar un único producto comprensible y sin simulaciones.

### Trabajo

1. Retirar botones, paneles y estados que no tengan comportamiento real.
2. Mostrar plan, riesgo, políticas, modelo, costo, permisos y resultado.
3. Unificar modales, confirmaciones, errores y estados de progreso.
4. Corregir foco, teclado, Escape, lector de pantalla y tamaños de texto.
5. Eliminar polling duplicado y carreras durante streaming.
6. Dividir Workbench, API, Settings y runtime Tauri por responsabilidad.

### Gate

- Ningún control visible es un stub.
- Flujo principal utilizable por teclado.
- Chat largo navegable y compositor siempre accesible.
- Errores explican causa, estado seguro y siguiente paso.
- Prueba satisfactoria con usuarios sin conocimiento previo.

## Fase 10 — Distribución y cadena de suministro

**Objetivo:** producir artefactos verificables y actualizaciones seguras.

### Trabajo

1. Separar build sin privilegios del job mínimo de firma.
2. Fijar acciones y herramientas críticas por versión inmutable.
3. Firmar instaladores, updater y sidecar.
4. Exigir updater, firma, `update.json`, SBOM, manifiesto, hashes y procedencia como
   conjunto exacto.
5. Verificar criptográficamente el conjunto antes de publicar.
6. Retirar el instalador heredado o declararlo obsoleto.
7. Regenerar metadatos sin artefactos históricos de AIVO.

### Gate

- Release reproducible desde checkout limpio.
- Artefactos alterados o incompletos son rechazados.
- Ninguna clave privada alcanza jobs no autorizados.
- Auditorías de dependencias sin vulnerabilidades críticas abiertas.

## Fase 11 — E2E real y pentest independiente

**Objetivo:** demostrar seguridad y funcionamiento en una máquina Windows limpia.

### Trabajo

1. Instalar, iniciar, configurar, conversar y ejecutar una acción gobernada.
2. Reiniciar y verificar persistencia.
3. Actualizar de N-1 a N y recuperar una actualización fallida.
4. Desinstalar y comprobar residuos.
5. Pentest de autorización, prompt injection, SSRF, rutas, junctions, plugins,
   IPC, Vault, updater, Fleet y auditoría.

### Gate

- Cero hallazgos críticos abiertos.
- Hallazgos altos corregidos o formalmente bloqueantes.
- Atestación ligada al commit y artefactos exactos.
- E2E repetible en VM limpia.

## Fase 12 — Lanzamiento controlado

**Objetivo:** pasar de candidato interno a disponibilidad pública gradualmente.

### Trabajo

1. Unificar README, changelog, roadmap y notas de versión.
2. Canal interno, luego beta privada y finalmente publicación gradual.
3. Supervisar fallos, latencia, fallbacks, costos, persistencia y actualizaciones.
4. Mantener rollback de versión y acciones sensibles en modo conservador.

### Gate final

- Periodo interno estable sin pérdida de datos ni bypass de autorización.
- Pentest aprobado.
- Actualización y rollback verificados.
- Artefactos firmados, reproducibles y auditables.

## Regla final

No se inicia una fase posterior porque exista código de la anterior. Se inicia
únicamente cuando su gate está verde y la evidencia queda registrada. Hasta
cerrar las fases 5–8 no se agregan proveedores, agentes, pantallas ni capacidades
grandes.
