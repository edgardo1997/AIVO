# Sentinel Intelligence Migration Baseline

## Información del Repositorio

| Campo | Valor |
|---|---|
| **Fecha** | 2026-07-29 |
| **Commit** | `dae492b` — Prepare Sentinel 1.0.0 release candidate |
| **Versión** | 1.0.0 (release candidate) |
| **Rama actual** | `feature/sentinel-intelligence-migration` (creada desde `codex/v1.0.0-rc.1`) |
| **Cambios pendientes** | Stashed (trabajo previo sin commit): modificaciones en `chat_tools.py`, `executor_service.py`, `__init__.py`, y otros archivos. La rama de migración parte del commit limpio. |

## Python

| Campo | Valor |
|---|---|
| **Versión** | 3.12.10 |
| **Ejecutable** | `C:\Users\edgar\AppData\Local\Programs\Python\Python312\python.exe` |
| **OS** | Windows (win32) |

## Dependencias (125 paquetes)

### Core
- fastapi==0.139.0
- uvicorn==0.34.0
- pydantic==2.10.3
- pydantic-settings==2.7.0
- starlette==1.3.1
- httpx==0.28.1
- httptools==0.8.0
- python-multipart==0.0.32
- websockets==16.0

### AI/ML
- openai==2.48.0

### Seguridad
- cryptography==49.0.0
- bcrypt==5.0.0
- PyJWT==2.13.0
- defusedxml==0.7.1
- bandit==1.8.6

### Base de datos
- SQLAlchemy==2.0.36
- aiosqlite==0.20.0
- alembic==1.14.0

### Sistema
- psutil==6.1.0
- PyYAML==6.0.3
- watchfiles==1.2.0

### Testing
- pytest (con plugins: pytest-asyncio, pytest-timeout, pytest-cov)
- coverage==7.15.1

### Documentos/Archivos
- PyMuPDF==1.28.0
- Pillow==12.3.0
- python-docx==1.1.2
- reportlab==4.2.5
- beautifulsoup4==4.12.2

### Otros
- GitPython==3.1.51
- CacheControl==0.14.4
- pyinstaller==6.21.0
- pip-audit==2.10.1

## Configuración

### Variables de Entorno
| Variable | Valor |
|---|---|
| `SENTINEL_API_KEY_OPENROUTER` | Configurada (sk-or-v1-...) |
| `SENTINEL_SESSION_TOKEN` | Definida en `.env` |

### Providers Configurados
Según `sidecar/services/ai_service.py` (`FREE_PROVIDERS`) y `sentinel/core/model_router.py` (`BUILTIN_PROVIDERS`):

| Provider ID | Modelo Default | Tool Calling | Task Types |
|---|---|---|---|
| `nvidia-nemotron` | `nvidia/nemotron-3-super-120b-a12b` | ❌ No soportado | REASONING, ANALYSIS, CREATIVE |
| `openrouter` | `deepseek/deepseek-v4-flash:free` | ❌ No soportado (nunca se envía) | Todos |
| `deepseek` | `deepseek-chat` | ❌ | REASONING, CODE |
| `openai` | `gpt-4o` | ❌ | Todos |
| `anthropic` | `claude-3.5-sonnet` | ❌ (usa proxy OpenAI) | REASONING, CODE |
| `github_models` | `gpt-4o-mini` | ❌ | REASONING, CREATIVE |
| `google` | `gemini-2.0-flash-exp` | ❌ | REASONING, ANALYSIS |
| `sentinel_local` | `Qwen3-1.7B-Q8_0.gguf` | ❌ | QUICK, LOCAL |
| `ollama` | `qwen2.5-coder:1.5b` | ❌ | QUICK, LOCAL |

### Routing Strategy
- Default: `priority`
- Task type map: desactivado (nunca se lee en `select()`)
- Fallback strategy: por defecto

### Runtime Config
- `SENTINEL_ENABLE_ACL = 0` (en tests)
- `SENTINEL_ENABLE_FLEET_STARTUP = 0` (en tests)
- Rate limiting: activo (free tier: user=10/min, session=5/min)

## Estado Actual

### Lo que funciona
- Pipeline completo de ejecución (Intent → Plan → Risk → Decision → ToolGateway → Executor)
- Chat básico con modelos vía `AIService.chat()`
- Ejecución de herramientas (launch, command, kill, restart)
- Seguridad multi-capa (auth, consent, policy, risk, grounding)
- Rate limiting por tier/usuario/sesión/herramienta
- Multi-model routing por task type
- Streaming de chat
- Multi-agent (pipeline separado)
- Cost tracking (SQLite)
- Grounding con cache
- Circuit breaker por herramienta

### Lo que NO funciona o está incompleto
- **Tool calling nativo**: `ModelRouter` nunca envía `tools`/`functions` a la API — solo chat completion
- **Model Registry**: No existe metadata de capacidades por modelo
- **Budget enforcement**: `check_budgets()` existe pero nunca se llama en pipeline
- **Offline queue**: `_sync_offline_item()` es no-op
- **Context window en fallback**: No se re-maneja si el modelo fallback tiene menos contexto
- **CRITICAL_TOOLS**: Vacío en RiskClassifier
- **Conversation continuity**: No hay estado cross-model

## Observaciones
- El pipeline de seguridad es maduro (~10 gates antes de ejecutar una tool)
- La deuda técnica principal está en el sistema de modelos (sin capacidades, sin tool calling, sin registry)
- La rama `feature/sentinel-intelligence-migration` se creó desde el commit `dae492b` (limpio)
- Los cambios de trabajo previo (fix en `chat_tools.py`) están stashed, no incluidos en esta baseline
