# Arquitectura
## Actual verificada
Existen Orchestrator, ExecutionPipeline, ToolExecutionGuard, ToolGateway, PolicyEngine, ConfirmationBroker, SQLite y auditoría. Hay rutas legacy de pending actions: su retiro está pendiente.
## Objetivo aprobado
Una sola cadena: API/Identity → Intent → Planning/Risk/Policy → ConfirmationBroker → ExecutionPipeline → Guard → Gateway → Executor → Audit. Se prohíben gateways alternativos, flags de consentimiento y componentes desconectados.
