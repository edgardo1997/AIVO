# Sentinel CTO Manual

Versión 0.1 | 2026-08-02 | Estado: autoridad documental propuesta

## Propósito y autoridad

Este manual permite trabajar en Sentinel sin depender de conversaciones históricas. Establece principios, decisiones y evidencia exigida. No sustituye evidencia runtime. Si el manual contradice comportamiento productivo verificado, debe abrirse una discrepancia y corregirse la documentación o la implementación mediante una decisión arquitectónica explícita.

## Identidad

Sentinel es una capa inteligente local-first y gobernada entre el usuario, los modelos, las herramientas y el sistema operativo. No es un chatbot, un wrapper de APIs ni un ejecutor autónomo sin control humano.

Su cadena oficial objetivo es: Intención → Decisión → Política → Consentimiento → ExecutionPipeline → ToolExecutionGuard → ToolGateway → Ejecutor → Verificación → Memoria/Feedback/Auditoría.

## Estado actual verificado

El repositorio contiene React/Vite, Tauri/Rust, sidecar FastAPI/Python y núcleo `sentinel/`. `npm run build` pasó el 2026-08-02 y `pytest -m security` pasó con 236 pruebas. Hay ExecutionPipeline, Orchestrator, ToolGateway, ToolExecutionGuard, PolicyEngine, ConfirmationBroker, SQLite, automatizaciones, modelos, auditoría y plugins.

La autoridad de ExecutionGrant durable está implementada como esquema/repositorio y pruebas de SQLite, pero **NOT VERIFIED como autoridad conectada en todas las rutas de producción**. `approve_execution()` y pending actions legacy permanecen durante la migración. Instalación limpia, sidecar desktop, updater, recuperación real y proveedores reales: **NOT VERIFIED**.

## Principios no negociables

1. Ningún booleano, flag interno, nivel implícito o UI concede autoridad.
2. Toda acción sensible usa identidad, sesión, plan, herramienta y parámetros ligados a un grant durable de un solo uso.
3. Los fallos de identidad, política, broker o persistencia fallan cerrados.
4. La auditoría conserva creación, decisión, consumo, rechazo y expiración.
5. El estado prometido persiste y se prueba tras reinicio.
6. Un archivo, mock o UI no prueba wiring productivo.

## Prioridad de ingeniería

Seguridad crítica, integridad de datos, autoridad de ejecución, persistencia, fiabilidad, validación de producción, rendimiento, UX y finalmente funciones nuevas.

## Navegación

- [Visión](01_VISION_AND_IDENTITY.md)
- [Filosofía](02_PRODUCT_PHILOSOPHY.md)
- [Arquitectura](03_ARCHITECTURE.md)
- [Ingeniería](04_ENGINEERING_RULES.md)
- [Seguridad](05_SECURITY_STANDARD.md)
- [Producto](06_PRODUCT_AND_COMMERCIAL.md)
- [Definition of Done](07_DEFINITION_OF_DONE.md)
- [Decisiones](08_DECISION_FRAMEWORK.md)
- [Refactor](09_REFACTOR_AND_DELETION_POLICY.md)
- [Rechazo](10_IMPLEMENTATION_REJECTION_RULES.md)
- [Reportes](11_REPORTING_STANDARD.md)
- [Trazabilidad](TRACEABILITY_MATRIX.md)

## Reglas para agentes

Inspeccionar Git, diff, rutas de producción y pruebas antes de afirmar progreso. Preservar worktree ajeno. No activar migraciones parciales. Marcar `NOT VERIFIED` donde falte evidencia reproducible. Un bloqueo debe incluir archivo, línea, contrato, evidencia, impacto y decisión mínima requerida.
