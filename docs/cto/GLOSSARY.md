# Glosario

| Término | Sentinel | Error común |
|---|---|---|
| Orchestrator | Coordina intención, plan y resultado. | Confundirlo con autoridad de consentimiento. |
| ExecutionPipeline | Ruta nominal gobernada de ejecución. | Suponer que toda ruta la usa. |
| ToolGateway | Registro e invocación de herramientas. | Llamarlo directamente desde routers. |
| ToolExecutionGuard | Frontera de riesgo, política y confirmación. | Tratarlo como una UI. |
| ConfirmationBroker | Emisor objetivo de autoridad durable. | Usar pending actions como grant. |
| ExecutionGrant | Autorización ligada a efectos. | Considerarlo globalmente integrado. |
| PlanApprovalGrant | Autorización durable de un plan. | Reutilizarlo tras cambiar plan. |
| StepExecutionGrant | Autorización de un paso. | Omitir step index. |
| plan_hash | Huella del plan inmutable. | Hashear texto no canónico. |
| params_hash | Huella canónica de parámetros/efecto. | Hashear solo argumentos. |
| identity_hash | Huella de identidad. | Sustituirla con un rol. |
| session_id | Contexto de sesión. | Dejarlo vacío en acción sensible. |
| binding | Campos que deben coincidir al consumir. | Validar solo tool. |
| replay | Reuso de una autorización. | Defenderse solo borrando registros. |
| atomic | Una transición con un único ganador. | Get y update separados. |
| durable | Conservado tras reinicio. | Mantenerlo en singleton. |
| fail-closed | Rechazar si falta seguridad. | Fallback directo. |
| policy | Regla central de permiso/riesgo. | Convención de router. |
| risk | Clasificación del efecto. | Declaración UI. |
| audit | Evidencia de eventos. | Log efímero. |
| simulation | Predicción previa de efecto. | Consentimiento. |
| grounding | Evidencia previa a afirmar/actuar. | Ejecución de herramienta. |
| local-first | Función local por defecto. | Sin red bajo cualquier condición. |
| production wiring | Conexión al runtime real. | Archivo importable. |
| migration | Evolución versionada de esquema. | ALTER manual. |
| idempotent | Repetición sin efecto incorrecto. | Solo no lanzar excepción. |
| rollback | Recuperación a estado seguro. | Reusar aprobación. |
| plugin | Extensión registrada. | Autoridad autoasignada. |
| model registry | Catálogo de modelos. | Garantía de proveedor disponible. |
| observability | Señales para operar sistema. | Sustituto de auditoría. |
| commercial ready | Instalación, soporte y actualización demostrables. | Build compilado. |
