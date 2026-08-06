# Auditoría de ProviderManager / ModelRouter / Routing — Sentinel

**Fecha:** 2026-08-05  
**Rama:** `feature/technical-phase-completion`  
**Commit base:** `67db79f`  

---

## 1. Componentes identificados

| Componente | Fuente de verdad | Responsabilidad | Duplicación | Riesgo | Acción |
|------------|------------------|-----------------|-------------|--------|--------|
| `sentinel/providers/provider_manager.py` | Claves API + config OpenAI | Gestión de clientes, streaming, llamada a proveedores, integración CloudAuthority | Config en `ai_service.py` | Medio | Canonicalizar como única puerta de llamada |
| `sentinel/core/model_router.py` | Modelos registrados + capacidades | Selección de proveedor/modelo, routing por task type, fallback, CloudAuthority | Lógica similar en `routing/provider_selector.py` | Medio | Consolidar con `ProviderSelector` |
| `sentinel/core/router_types.py` | BUILTIN_PROVIDERS | Tipos y constantes de proveedores | Capacidades duplicadas en `model_registry.py` | Bajo | Normalizar |
| `sentinel/core/model_registry.py` | SQLite `stored_models` | Registro y búsqueda de modelos por capacidad | Ninguna | Bajo | Mantener |
| `sentinel/routing/provider_selector.py` | Puntuación heurística | Selección inteligente por costo/salud/capacidad | Parcial con `ModelRouter` | Medio | Deprecar o fusionar |
| `sentinel/routing/fallback_manager.py` | Cadenas configuradas | Ejecución de fallback con circuit breaker | Ninguna | Bajo | Reutilizar |
| `sentinel/core/provider_health.py` | Health checks periódicos | Estado de salud de proveedores | Ninguna | Bajo | Mantener |
| `sentinel/core/provider_performance.py` | Métricas agregadas | Latencia, costo, fallos | Ninguna | Bajo | Mantener |
| `sentinel/core/cost_tracker.py` | Presupuestos SQLite | Cost tracking, budgets | Parcial con `ContextBudgetManager` | Medio | Integrar en router |
| `sentinel/core/context_budget.py` | Límites de tokens | Presupuesto de contexto | Ninguna | Bajo | Mantener |
| `sentinel/security/cloud_authority.py` | Autorización cloud | Decidir si cloud permitido | Ninguna | Medio | Exigir en todo bypass |
| `sentinel/local_model/runtime.py` | Proceso llama.cpp | Runtime local, descarga, health | Ninguna | Medio | Distinguir procesos vs. listo |
| `sidecar/services/ai_service.py` | Config de AI | Chat, análisis, embeddings bypass | ModelRouter y ProviderManager | Alto | Eliminar bypasses |
| `sentinel/core/knowledge_base.py` | Embedding provider | OpenRouter/Ollama embeddings | ProviderManager | Alto | Eliminar bypass OpenAI |
| `sentinel/core/model_discovery.py` | Discovery endpoints | Detección de modelos local/cloud | Ninguna | Medio | Mantener como discovery |

---

## 2. Llamadas directas detectadas

| Archivo | Llamada | Destino | Riesgo | Acción |
|---------|---------|---------|--------|--------|
| `sidecar/services/ai_service.py:465` | `client.chat.completions.create` | OpenAI genérico | **P0** | Exigir CloudAuthority y usar `ProviderManager` |
| `sidecar/services/ai_service.py:663` | `client.chat.completions.create` | OpenAI genérico | **P0** | Exigir CloudAuthority y usar `ProviderManager` |
| `sidecar/services/ai_service.py:699` | `_make_client` instancia `OpenAI` | Config arbitraria | **P0** | Eliminar fabricación directa de cliente |
| `sentinel/core/knowledge_base.py:72` | `OpenAI(api_key=...)` | OpenRouter embedding | **P0** | Migrar a `ProviderManager` |
| `sentinel/core/knowledge_base.py:88` | `client.embeddings.create` | OpenRouter embedding | **P0** | Migrar a `ProviderManager` |
| `sentinel/local_model/runtime.py:244` | `urllib.request.urlopen` | Warmup local | P2 | Añadir timeout + health |
| `sentinel/local_model/runtime.py:262` | `urllib.request.urlopen` | Health check | P2 | Integrar en `ProviderHealthChecker` |
| `sentinel/core/model_discovery.py` | `httpx.get` | Discovery | P2 | Mantener como discovery |
| `sentinel/core/provider_health.py` | `httpx.get` | Health check | Bajo | Mantener |

---

## 3. Responsabilidades objetivo

### ProviderRegistry (`sentinel/core/model_registry.py`)
- Registrar, listar, buscar modelos por capacidad.
- Resolver configuración declarada.
- No decidir presupuesto ni autoridad.

### ProviderManager (`sentinel/providers/provider_manager.py`)
- Estado de proveedor, credenciales, health, lifecycle, adapters, rate limits, circuit breaker.
- Única puerta para llamadas a proveedores cloud.
- No elegir modelo final.

### ModelRouter (`sentinel/core/model_router.py` + `routing/provider_selector.py`)
- Evaluar requisitos, filtrar candidatos, ordenar, seleccionar, producir `RoutingDecision` explicable.
- No autorizar cloud, no leer secretos directamente, no ejecutar herramientas.

### CloudAuthority (`sentinel/security/cloud_authority.py`)
- Decidir cloud permitido, proveedor permitido, alcance, duración, presupuesto.
- El router nunca puede ignorarlo.

---

## 4. Contratos propuestos

### ModelRequest

```python
class ModelRequest(BaseModel):
    request_id: str
    correlation_id: str
    user_id_hash: str
    session_id_hash: str
    task_type: str
    language: str | None
    required_capabilities: list[str]
    preferred_capabilities: list[str]
    privacy_requirement: str = "local_preferred"  # local_only, local_preferred, cloud_allowed
    local_only: bool = False
    cloud_allowed: bool = False
    max_cost: float | None = None
    max_latency_ms: int | None = None
    context_size: int | None = None
    streaming_required: bool = False
    tool_calling_required: bool = False
    vision_required: bool = False
    structured_output_required: bool = False
    provider_preference: str | None = None
    model_preference: str | None = None
    fallback_policy: str = "authorized_cloud"  # none, same_provider, local_only, authorized_cloud, ordered_chain
```

### RoutingDecision

```python
class RoutingDecision(BaseModel):
    selected_provider: str
    selected_model: str
    candidate_count: int
    selection_reason_code: str
    capabilities_matched: list[str]
    capabilities_missing: list[str]
    cloud_used: bool
    authority_reference: str | None
    estimated_cost: float | None
    estimated_latency_ms: int | None
    fallback_chain: list[str]
    confidence: str  # high, medium, low
```

---

## 5. Capacidades normalizadas

```text
chat
reasoning
coding
tool_calling
structured_output
vision
audio_input
audio_output
embeddings
streaming
long_context
json_schema
function_calling
local
cloud
```

Origen: `declared` / `probed` / `verified` / `unknown`.

---

## 6. Estado permitido provisional

- Provider inventory = **COMPLETADO**
- ProviderManager = **CONSOLIDADO PARCIAL**
- ModelRouter = **CONSOLIDADO PARCIAL**
- Cloud Authority integration = **PENDIENTE DE AUDIT EN BYPASSES**
- Local First = **VERIFICADO**
- Fallback = **ENDURECIDO PARCIAL**
- Adapters = **CLASIFICADOS PARCIAL**
- Migración de rutas legacy = **PARCIAL**

---

## 7. Avance implementado

- Contratos canónicos: `sentinel/core/model_schemas.py` (`ModelRequest`, `RoutingDecision`, etc.).
- `sentinel/core/provider_registry.py` responsabilidad limitada a metadata.
- `ProviderManager` contratos canónicos: `execute_inference`, `execute_inference_stream`, `execute_embedding`, `get_provider_state`, `get_model_state`.
- `ModelRouter.route` / `execute` / `execute_stream` canonicalizados.
- `sentinel/core/budget.py` reserva atómica con concurrencia probada.
- Circuit breaker testeado.
- Embeddings con autoridad obligatoria (`local_only` por defecto).
- Tool calling: adaptador normaliza propuestas, no ejecuta.
- AIService: eliminados bypasses directos OpenAI.
- `create_embedding_provider` no usa OpenRouter por defecto.

## 8. Deuda restante

- [x] Integrar `BudgetManager` en `ModelRouter` para filtrar por presupuesto en caliente.
- [x] `FallbackValidator` con revalidación de authority, budget, capabilities, context.
- [x] `MetricsStore` integrado en `ModelRouter.route` y `ProviderManager.execute_inference`.
- [x] Runtime local compartido (`get_local_runtime`) en `ProviderManager`.
- [x] Presupuesto reservado antes de selección.
- [x] `AdapterContract` con clasificación SUPPORTED/EXPERIMENTAL/DISABLED/UNSUPPORTED.
- [x] `MetricsStore` con esquema canónico y guardrails de privacidad.
- [x] `ContextWindowValidator` y `model_errors.py` estables.
- [x] `FallbackManager` invoca `FallbackValidator` para candidatos secundarios.
- [x] Tests de contrato público para `chat`.
- [x] Fakes adapters para tests canónicos.
- [x] `call_provider` es wrapper delegado a `execute_inference`.
- [x] `_do_inference` contiene lógica canónica.
- [x] Test de contrato público `call_provider`.
- [x] `ModelRouter._call_provider` loguea deprecación.
- [x] `ModelRouter._chat_canonical` con ruta `route` → `execute`.
- [x] Feature flag `SENTINEL_CANONICAL_CHAT` para pruebas comparativas.
- [x] Inventario de migración legacy en `MODEL_LEGACY_MIGRATION.md`.
- [x] `RoutingError` usado correctamente en respuestas canónicas.
- [x] `_call_provider` delega en `execute_inference`.
- [x] `chat_with_provider` usa `route` + `execute` canónico.
- Migrar embeddings OpenRouter a adapters externos.
- Tests de adapter contract suite.
- Health/readiness real para modelo local (proceso vs. listo).
- Context window validation integrado.
- Fallback rechecks authority/budget en cadena.

## 9. Suite

- Python: 3272 passed
- JS: 154 passed
- Rust: 5 passed
- Clippy: OK
