# FASE 2 — COMPLETION REPORT

## Tool Calling Real

**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-29  

---

## ¿Qué archivos fueron creados?

| Archivo | Propósito |
|---|---|
| `sentinel/core/tool_schema_adapter.py` | Convierte ToolSpec interno a esquemas compatibles con OpenAI |
| `sidecar/tests/test_tool_calling.py` | 27 tests de schema adapter, ModelRouter tool calling, protección |
| `docs/intelligence_migration/phase_2_tool_calling.md` | Documentación completa de la Fase 2 |

## ¿Qué archivos fueron modificados?

| Archivo | Cambios |
|---|---|
| `sentinel/core/model_router.py` | +`set_tool_gateway()`, +`_validate_tool_call_compatibility()`, +`_execute_tool_call()`, +`_handle_tool_calls()`, +`chat_with_tools()`, modificación de `_call_provider()` para aceptar tools |

## ¿Cómo funciona ahora Tool Calling?

**Antes (Fase 1):**
```
Model → Texto → Sentinel interpreta intención → ToolGateway
```

**Ahora (Fase 2):**
```
Model (supports_tool_calling=True)
  → Tool Call estructurado (JSON)
  → ModelRouter._handle_tool_calls()
    → Valida compatibilidad del modelo
    → ToolGateway.execute()
      → Identity Gate → Authorization Gate → Consent Gate
      → Policy Engine → Risk Assessment → Executor
    → Resultado se agrega a la conversación
    → Model recibe resultado → respuesta final al usuario
```

El flujo completo en `chat_with_tools()`:

1. Convierte ToolSpecs a schema OpenAI
2. Selecciona modelo compatible con tool calling
3. Envía mensajes + tools al LLM
4. Si hay tool_calls en la respuesta:
   - Valida que el modelo tenga `supports_tool_calling=True`
   - Ejecuta cada tool via ToolGateway (con pipeline de seguridad completo)
   - Agrega resultados a la conversación
   - Reenvía al LLM para respuesta final
5. Si no hay tool_calls → devuelve respuesta de texto normal

## ¿Qué modelos soportan herramientas?

Actualmente **ningún modelo por defecto** tiene `supports_tool_calling=True`. La Fase 2 establece la infraestructura:

- ModelRegistry ya soporta el filtro `["tool_calling"]`
- `select_by_capability(["tool_calling"])` encuentra modelos compatibles
- `chat_with_tools()` verifica `find_candidates(["tool_calling"])` antes de enviar tools
- Modelos con `supports_tool_calling=True` recibirán tools y tool_choice="auto"

Para activar tool calling en un modelo, basta con registrarlo con `supports_tool_calling=True`.

## ¿Qué ocurre cuando un modelo incompatible intenta usar tools?

**Validación estricta:** `_validate_tool_call_compatibility()` consulta el ModelRegistry:

- Sin registry → permitido (backward compatibility)
- Modelo no encontrado → permitido (backward compatibility)
- `supports_tool_calling=True` → permitido
- `supports_tool_calling=False` → **RECHAZADO**

El rechazo genera:
```python
RuntimeError: Tool calling rejected: model 'nemotron' (provider=nvidia-nemotron)
does not support tool calling
```

No se ejecuta NINGUNA herramienta. El error es controlado y manejable por el caller.

Además, los tools con `status=DISABLED` son filtrados por `to_openai_tools()` y nunca llegan al modelo.

## ¿Todos los tests pasan?

**68 tests nuevos** (Fase 1 + Fase 2): **68/68 pasan**

```
tests/test_model_registry.py .............. 30 passed
tests/test_model_router_phase1.py ........ 11 passed
tests/test_tool_calling.py ............... 27 passed
```

**Suite completa:** 2869 passed, 2 failed, 1 skipped
- Fallos pre-existentes no relacionados:
  - `test_backend_has_no_shell_or_free_command_execution` (archivo renombrado)
  - `test_similar_texts_have_higher_sim` (inconsistente — pasa individualmente)
- **0 regresiones** causadas por Fase 2

## ¿Sentinel mantiene el pipeline de seguridad?

**SÍ.** Toda ejecución de herramientas continúa pasando por el pipeline completo de ToolGateway:

```
Tool call
  → Identity Gate (autenticación requerida)
  → Authorization Gate (permisos)
  → Consent Gate (consentimiento del usuario)
  → Policy Engine (evaluación de políticas)
  → Risk Assessment (clasificación de riesgo)
  → Grounding (restricciones de contexto)
  → Circuit Breaker (protección contra fallos)
  → Executor (ejecución con timeout)
  → Quality Gate (escaneo de salida)
  → Auditoría (registro de todas las decisiones)
```

No se creó ningún nuevo camino de ejecución. `_execute_tool_call()` llama a `ToolGateway.execute()` que aplica el pipeline existente.

---

## Criterios de Aceptación — Verificación

| Criterio | Estado |
|---|---|
| ✅ ModelRouter envía tools solamente a modelos compatibles | Implementado en `_call_provider()`: tools solo cuando se pasan explícitamente |
| ✅ Modelos con Tool Calling pueden generar llamadas estructuradas | `chat_with_tools()` orquesta el ciclo completo |
| ✅ Las llamadas pasan por ToolGateway | `_execute_tool_call()` usa `ToolGateway.execute()` |
| ✅ Ningún modelo puede ejecutar herramientas directamente | No hay atajo — toda ejecución pasa por ToolGateway |
| ✅ Modelos sin Tool Calling continúan funcionando como chat | `chat_with_tools()` cae a `chat()` si no hay modelos compatibles |
| ✅ Existen tests automatizados | 27 tests específicos de tool calling |
| ✅ Sentinel mantiene seguridad existente | Pipeline de seguridad intacto, no modificado |
| ✅ Modelos incompatibles son rechazados con error controlado | `_validate_tool_call_compatibility()` con RuntimeError descriptivo |
| ✅ Tools DISABLED nunca llegan al modelo | `to_openai_tools()` filtra por status |
| ✅ Límite de recursión protege contra loops infinitos | `max_tool_rounds` (default 5) |
