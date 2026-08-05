import logging
import uuid
from typing import Iterator, Optional
from repositories.ai_repository import AIRepository
from sentinel.core.model_router import ModelRouter, TaskType, classify_provider_error
from sentinel.core.context_window import ContextWindowManager, count_messages_tokens
from sentinel.core.context_budget import ContextBudgetManager, RequestPurpose
from sentinel.conversation import ConversationAvailabilityLayer, ConversationRequest, SentinelCoreConversation
from services import language_service, input_understanding_service

log = logging.getLogger("sentinel.ai_service")

SYSTEM_PROMPT = """Eres la inteligencia conversacional de Sentinel, una plataforma que puede analizar el equipo, abrir aplicaciones, ejecutar scripts y modificar archivos mediante un pipeline gobernado (intención → plan → políticas → ejecución → auditoría). Sentinel sí puede abrir aplicaciones instaladas cuando el usuario lo solicita mediante el pipeline. Si pregunta cómo abrir una aplicación, indícale que escriba una instrucción directa como «Abre WhatsApp»; Sentinel buscará la aplicación y la abrirá si está instalada y las políticas lo permiten. Nunca digas que Sentinel no tiene acceso a aplicaciones. Nunca afirmes que una acción ocurrió si no recibiste un resultado de herramienta que lo confirme. Cuando el usuario pida algo que Sentinel puede hacer, dile que sí puede hacerlo y reformula su petición como una instrucción directa para que el pipeline la procese. Si el pipeline ya ejecutó una acción y te pasaron el resultado, explícalo con precisión. Si no hay resultado de pipeline, ayuda con conocimiento general o dile al usuario que pida la acción directamente. Sé práctico y conciso. Responde en el mismo idioma del usuario."""

ANALYZE_PROMPT = """You are a system analysis AI. Analyze the provided metrics and identify issues, trends, and recommendations. Be specific and actionable. Format your response as bullet points covering: 1) Critical Issues, 2) Warnings, 3) Recommendations."""


FREE_PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek V4 Flash (Gratis con key)",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_required": True,
        "default_model": "deepseek/deepseek-v4-flash:free",
        "description": "Modelo gratuito vía OpenRouter — requiere API key gratuita",
        "signup_url": "https://openrouter.ai/keys",
    },
    "nvidia-nemotron": {
        "label": "NVIDIA Nemotron (Gratis con key)",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_required": True,
        "default_model": "nvidia/nemotron-3-super-120b-a12b",
        "description": "Modelo gratuito de NVIDIA — requiere API key gratuita",
        "signup_url": "https://build.nvidia.com/settings/api-keys",
    },
    "sentinel_local": {
        "label": "Sentinel Local (predeterminado)",
        "base_url": "http://127.0.0.1:11435/v1",
        "api_key_required": False,
        "default_model": "Qwen3-1.7B-Q8_0.gguf",
        "description": "Modelo privado administrado por Sentinel; funciona sin internet después de instalarse",
        "signup_url": "",
    },
    "openrouter": {
        "label": "OpenRouter (modelos gratis)",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_required": True,
        "default_model": "deepseek/deepseek-v4-flash:free",
        "description": "28+ modelos gratuitos con una sola key",
        "signup_url": "https://openrouter.ai/keys",
    },
    "groq": {
        "label": "Groq (inferencia rápida)",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_required": True,
        "default_model": "llama-3.3-70b-versatile",
        "description": "Inferencia ultrarrápida, 30 req/min gratis",
        "signup_url": "https://console.groq.com/keys",
    },
    "gemini": {
        "label": "Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_required": True,
        "default_model": "gemini-2.5-flash",
        "description": "Modelo gratuito de Google, sin costo",
        "signup_url": "https://aistudio.google.com/apikey",
    },
    "github_models": {
        "label": "GitHub Models",
        "base_url": "https://models.inference.ai.azure.com",
        "api_key_required": True,
        "default_model": "gpt-4o-mini",
        "description": "Modelos gratis con cuenta GitHub",
        "signup_url": "https://github.com/settings/tokens",
    },
    "cerebras": {
        "label": "Cerebras (rápido)",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_required": True,
        "default_model": "llama-3.3-70b",
        "description": "Inferencia rápida, modelo gratuito",
        "signup_url": "https://cloud.cerebras.ai/",
    },
    "mistral": {
        "label": "Mistral (gratis)",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_required": True,
        "default_model": "mistral-small-latest",
        "description": "API gratuita con límite generoso",
        "signup_url": "https://console.mistral.ai/api-keys/",
    },
    "nvidia": {
        "label": "NVIDIA NIM · Nemotron 3 Super",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_required": True,
        "default_model": "nvidia/nemotron-3-super-120b-a12b",
        "description": "Razonamiento, código y herramientas; endpoint gratuito para desarrollo",
        "signup_url": "https://build.nvidia.com/settings/api-keys",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_required": True,
        "default_model": "claude-sonnet-4",
        "description": "Modelos Claude para razonamiento y código (requiere proxy OpenAI-compatible)",
        "signup_url": "https://console.anthropic.com/",
    },
    "ollama": {
        "label": "Ollama (local, sin internet)",
        "base_url": "http://localhost:11434/v1",
        "api_key_required": False,
        "default_model": "llama3",
        "description": "100% local, privado, sin API key",
        "signup_url": "",
    },
}


class AIService:
    def __init__(
        self, repo: AIRepository = None, router: ModelRouter = None, context_manager: ContextWindowManager = None
    ):
        self.repo = repo or AIRepository()
        self._router = router
        self._context_manager = context_manager or ContextWindowManager()
        self._capability_registry = None
        self._vault = None
        self._audit = None
        self._cloud_authority = None
        self._conversation = ConversationAvailabilityLayer(SentinelCoreConversation(), _RuntimeCapabilities(self))

    def set_router(self, router: ModelRouter) -> None:
        self._router = router

    def set_cloud_authority(self, cloud_authority) -> None:
        self._cloud_authority = cloud_authority
        if self._router:
            self._router.set_cloud_authority(cloud_authority)

    def set_audit_service(self, audit_svc) -> None:
        self._audit = audit_svc

    def set_vault(self, vault) -> None:
        self._vault = vault
        self._migrate_legacy_key_to_vault()

    def load_provider_keys(self) -> None:
        if not self._router:
            return

        # 1. Cargar desde environment variables primero
        import os

        env_map = {
            "deepseek": "SENTINEL_API_KEY_DEEPSEEK",
            "nvidia-nemotron": "SENTINEL_API_KEY_NVIDIA",
            "nvidia": "SENTINEL_API_KEY_NVIDIA",
            "openrouter": "SENTINEL_API_KEY_OPENROUTER",
            "groq": "SENTINEL_API_KEY_GROQ",
            "gemini": "SENTINEL_API_KEY_GEMINI",
            "openai": "SENTINEL_API_KEY_OPENAI",
            "anthropic": "SENTINEL_API_KEY_ANTHROPIC",
            "github_models": "SENTINEL_API_KEY_GITHUB",
            "cerebras": "SENTINEL_API_KEY_CEREBRAS",
            "mistral": "SENTINEL_API_KEY_MISTRAL",
        }
        for provider_id, env_var in env_map.items():
            key = os.environ.get(env_var)
            if key:
                try:
                    self._router.set_api_key(provider_id, key)
                    log.info("Loaded API key for %s from env %s", provider_id, env_var)
                except KeyError:
                    pass

        # 2. Cargar desde vault (sobrescribe env vars si existen)
        if not self._vault:
            return
        for entry in self._vault.list_entries(category="ai_provider"):
            provider = entry.id.removeprefix("ai-provider-")
            value = self._vault.reveal_value(entry.id)
            if provider and value:
                try:
                    self._router.set_api_key(provider, value)
                except KeyError:
                    log.warning("Ignoring vault key for unknown provider %s", provider)

    def _migrate_legacy_key_to_vault(self) -> None:
        if not self._vault:
            return
        current = self.repo.load()
        key = current.pop("api_key", "")
        provider = current.get("provider", "")
        if key and key != "set" and provider:
            self._store_provider_key(provider, key)
        if "api_key" not in current or key:
            self.repo.save(current)

    def _store_provider_key(self, provider: str, key: str) -> None:
        from sentinel.core.vault import VaultEntry

        vault_id = f"ai-provider-{provider}"
        if self._vault.get_entry(vault_id):
            self._vault.update_entry(vault_id, value=key)
        else:
            self._vault.create_entry(
                VaultEntry(
                    id=vault_id,
                    name=f"{provider} API key",
                    category="ai_provider",
                    value=key,
                    masked=True,
                    rotatable=True,
                    notes="Managed automatically by Sentinel model routing",
                )
            )

    def set_capability_registry(self, registry) -> None:
        self._capability_registry = registry

    def conversation_capabilities(self) -> dict:
        return self._conversation.capabilities()

    def get_config(self) -> dict:
        cfg = self.repo.load()
        provider = cfg.get("provider", "sentinel_local")
        model = cfg.get("model") or self._get_default_model(provider)
        key_configured = bool(self._vault and self._vault.get_entry(f"ai-provider-{provider}"))
        if not key_configured and not self._vault:
            try:
                from modules import init_vault

                self._vault = init_vault()
                key_configured = bool(self._vault and self._vault.get_entry(f"ai-provider-{provider}"))
            except Exception as e:
                log.warning("Could not initialize vault for config check: %s", e)
        if not key_configured and self._router:
            key_configured = self._router.has_api_key(provider)
        provider_key_status = {}
        if self._vault:
            for entry in self._vault.list_entries(category="ai_provider"):
                pid = entry.id.removeprefix("ai-provider-")
                if pid:
                    provider_key_status[pid] = True
        if self._router:
            for provider_info in self._router.list_providers():
                pid = provider_info["id"]
                if self._router.has_api_key(pid):
                    provider_key_status[pid] = True
        return {
            "provider": provider,
            # Never send a secret or a magic placeholder back to the UI. The
            # boolean is enough to render the persisted state safely.
            "api_key": "",
            "api_key_configured": key_configured,
            "model": model,
            "base_url": cfg.get("base_url") or "",
            "strategy": getattr(self._router, "_strategy", "priority") if self._router else "priority",
            "preferred_provider": getattr(self._router, "_preferred_provider", None) if self._router else None,
            "free_providers": FREE_PROVIDERS,
            "provider_key_status": provider_key_status,
            "providers": self._router.list_providers() if self._router else [],
            "routing_config": self._router.get_routing_config() if self._router else {},
        }

    def get_providers_list(self) -> list:
        if self._router is None:
            from sentinel.core.model_router import BUILTIN_PROVIDERS

            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "requires_key": p.requires_key,
                    "is_local": p.is_local,
                    "default_model": p.default_model,
                    "task_types": [t.value for t in p.task_types],
                }
                for p in BUILTIN_PROVIDERS
            ]
        return self._router.list_providers()

    def get_routing_config(self) -> dict:
        if self._router is None:
            return {"preferred_provider": None, "strategy": "priority", "max_fallbacks": 5}
        return self._router.get_routing_config()

    def restore_config(self) -> None:
        if self._router is None:
            return
        cfg = self.repo.load()
        provider = cfg.get("provider")
        model = cfg.get("model")
        strategy = cfg.get("strategy", "priority")
        if provider and self._cloud_authority:
            spec = self._router._providers.get(provider)
            if spec and not spec.is_local and not self._cloud_authority.is_authorized(provider, model or ""):
                log.warning(
                    "Stored cloud provider %s is not authorized for execution; switching to local. "
                    "cloud_authorization_review_required=true",
                    provider,
                )
                provider = "sentinel_local"
                local_spec = self._router._providers.get(provider)
                model = local_spec.default_model if local_spec else ""
        if provider:
            self._router.set_preferred_provider(provider)
        if strategy:
            self._router.set_strategy(strategy)
        ttm = cfg.get("task_type_map")
        if ttm and isinstance(ttm, dict):
            self._router.set_task_type_map_from_dict(ttm)
        offline_mode = cfg.get("offline_mode")
        if offline_mode and self._router:
            self._router.set_offline_mode(offline_mode)
        log.info(
            "AI config restored: provider=%s model=%s strategy=%s task_type_map=%s",
            provider,
            model,
            strategy,
            bool(ttm),
        )
        if self._audit:
            self._audit.log_action(
                "config_restored",
                f"source=sqlite provider={provider} strategy={strategy}",
                user="local",
            )

    @staticmethod
    def validate_model(provider: str, model: str) -> dict:
        from sentinel.core.model_router import BUILTIN_PROVIDERS

        default_model = ""
        for p in BUILTIN_PROVIDERS:
            if p.id == provider:
                default_model = p.default_model
                break
        return {
            "valid": bool(model.strip()),
            "provider": provider,
            "model": model,
            "default_model": default_model,
        }

    def delete_provider_key(self, provider: str) -> bool:
        if self._vault:
            vault_id = f"ai-provider-{provider}"
            deleted = self._vault.delete_entry(vault_id)
        else:
            deleted = False
        if self._router:
            self._router.delete_api_key(provider)
        return deleted

    def set_config(self, cfg: dict) -> dict:
        current = self.repo.load()
        strategy = cfg.pop("strategy", None)
        api_key = cfg.pop("api_key", None)
        task_type_map = cfg.pop("task_type_map", None)
        offline_mode = cfg.pop("offline_mode", None)
        if isinstance(api_key, str):
            api_key = api_key.strip()
            if api_key == "set":
                api_key = None
        provider = cfg.get("provider") or current.get("provider", "sentinel_local")
        current.update({k: v for k, v in cfg.items() if v is not None})
        if strategy:
            current["strategy"] = strategy
            current["preferred_provider"] = provider
        current.pop("api_key", None)
        if task_type_map is not None:
            current["task_type_map"] = task_type_map
        self.repo.save(current)
        if api_key:
            if not self._vault:
                try:
                    from modules import init_vault

                    self._vault = init_vault()
                except Exception as e:
                    log.warning("Could not initialize vault for API key storage: %s", e)
            if self._vault:
                self._store_provider_key(provider, api_key)
            else:
                log.warning("Vault unavailable; API key not persisted")
        else:
            old_provider = current.get("provider", "")
            if old_provider and old_provider != provider:
                self.delete_provider_key(old_provider)
        if self._router:
            if api_key:
                self._router.set_api_key(provider, api_key)
            if strategy:
                self._router.set_strategy(strategy)
                self._router.set_preferred_provider(provider)
            if task_type_map is not None and isinstance(task_type_map, dict):
                self._router.set_task_type_map_from_dict(task_type_map)
            if offline_mode is not None:
                self._router.set_offline_mode(offline_mode)
                current["offline_mode"] = offline_mode
        if self._audit:
            self._audit.log_action(
                "config_changed",
                f"provider={provider} strategy={strategy} preferred={current.get('preferred_provider')}",
                user="local",
            )
        return {"status": "saved"}

    def chat(
        self,
        message: str,
        system_prompt: str = None,
        context: list = None,
        provider: str = None,
        model_override: str = None,
        purpose: str = "conversation",
        tool_result=None,
    ) -> dict:
        cfg = self.repo.load()
        task_type = self._task_type_for_message(message)

        messages = []
        messages.append({"role": "system", "content": system_prompt or SYSTEM_PROMPT})
        if context:
            for ctx in context:
                if isinstance(ctx, dict) and "role" in ctx and "content" in ctx:
                    messages.append(ctx)
        messages.append({"role": "user", "content": message})

        active_provider = provider or cfg.get("provider", "sentinel_local")
        model = model_override or cfg.get("model") or self._get_default_model(active_provider)
        managed = self._context_manager.manage(messages, model=model)
        managed_messages = managed["messages"]
        if managed["trimmed"] > 0 or managed["summarized"]:
            log.info(
                "Context window: %d→%d msgs, %d tokens, trimmed=%d summarized=%s",
                managed["original_count"],
                managed["final_count"],
                managed.get("total_tokens", 0),
                managed["trimmed"],
                managed["summarized"],
            )

        decision = language_service.resolve_language(message)
        understanding = input_understanding_service.resolve_input(message, context or [])
        ambiguity = input_understanding_service.make_decision(understanding)
        language_instruction = language_service.build_language_instruction(decision)
        managed_messages[0]["content"] = (managed_messages[0]["content"] or "") + "\n\n" + language_instruction

        request = ConversationRequest(
            message=message,
            context=context or [],
            purpose=purpose,
            tool_result=tool_result,
        )

        def _run_chat(msgs):
            if not self._router:
                raise RuntimeError("AI router not configured; direct provider calls are disabled")
            old_preferred = None
            if provider and self._router:
                old_preferred = getattr(self._router, "_preferred_provider", None)
                self._router.set_preferred_provider(provider)
            try:
                result = self._router.chat(msgs, task_type=task_type)
                return {
                    "response": result["response"],
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                }
            except RuntimeError as exc:
                # The local runtime starts asynchronously. Do not preserve a
                # stale negative availability result for the first chat turn.
                if "available provider" in str(exc).lower() or "unavailable" in str(exc).lower():
                    try:
                        from services.local_model_service import runtime as local_model_runtime

                        # Startup happens in the background during application
                        # boot. If the first prompt wins that race, wait for the
                        # installed runtime here and retry once. This never
                        # downloads a model.
                        local_model_runtime.start_if_installed()
                        local = self._router.provider_availability("sentinel_local", refresh=True)
                        if local.available:
                            result = self._router.chat(msgs, task_type=task_type)
                            return {
                                "response": result["response"],
                                "provider": result.get("provider"),
                                "model": result.get("model"),
                            }
                    except Exception:
                        log.debug("Sentinel local availability refresh failed", exc_info=True)
                fallback_provider = cfg.get("provider", "sentinel_local")
                configured_provider_has_key = bool(self._router and self._router.has_api_key(fallback_provider))
                if not configured_provider_has_key:
                    try:
                        ollama_avail = self._router.provider_availability("ollama", refresh=True)
                        if ollama_avail.get("available"):
                            log.info("Ollama detectado como fallback temporal")
                            self._router.set_api_key("ollama", "ollama")
                            result = self._router.chat(msgs, task_type=task_type)
                            return {
                                "response": result["response"],
                                "provider": result.get("provider"),
                                "model": result.get("model"),
                            }
                    except Exception:
                        log.debug("Local model recovery unavailable", exc_info=True)
                raise
            finally:
                if old_preferred is not None and self._router:
                    self._router.set_preferred_provider(old_preferred)

        def advanced_chat():
            first = _run_chat(managed_messages)
            validation = language_service.validate_response_language(first["response"], decision)
            if validation.valid or not decision.translation_fallback_enabled:
                return {**first, "language_decision": decision, "language_validation": validation, "input_understanding": understanding, "ambiguity_decision": ambiguity}

            # One bounded correction attempt; never repeat tool calls or actions.
            corrected = managed_messages.copy()
            corrected.append({
                "role": "system",
                "content": language_service.build_correction_prompt(decision, validation),
            })
            second = _run_chat(corrected)
            return {
                **second,
                "language_decision": decision,
                "language_validation": validation,
                "input_understanding": understanding,
                "ambiguity_decision": ambiguity,
                "response_language_corrected": True,
            }

        return self._conversation.respond(request, advanced=advanced_chat).to_dict()

    def stream_chat(
        self,
        message: str,
        system_prompt: str = None,
        context: list = None,
        purpose: str = "conversation",
        tool_result=None,
        explicit_provider: str = None,
        explicit_model: str = None,
        correlation_id: Optional[str] = None,
    ) -> Iterator[dict]:
        """Stream an answer while preserving router selection and safe fallback."""
        cfg = self.repo.load()
        model = cfg.get("model") or self._get_default_model(cfg.get("provider", "sentinel_local"))
        messages = [{"role": "system", "content": system_prompt or SYSTEM_PROMPT}]
        messages.extend(
            item for item in (context or []) if isinstance(item, dict) and "role" in item and "content" in item
        )
        if model == "Qwen3-1.7B-Q8_0.gguf" and not message.startswith("<no_think>"):
            message = f"<no_think>{message}"
        messages.append({"role": "user", "content": message})
        try:
            request_purpose = RequestPurpose(purpose)
        except ValueError:
            request_purpose = RequestPurpose.CONVERSATION
        budget = ContextBudgetManager().budget_for(model, purpose=request_purpose)
        # max_input_tokens is the model-aware input cap; ContextWindowManager
        # owns the generation reserve and actual token counting/trimming.
        local_prompt_budget = budget.max_input_tokens
        managed_messages = self._context_manager.manage(messages, model=model, max_tokens=local_prompt_budget)[
            "messages"
        ]
        request = ConversationRequest(
            message=message,
            context=context or [],
            purpose=purpose,
            tool_result=tool_result,
        )
        correlation_id = correlation_id or str(uuid.uuid4())

        if self._router is not None:
            try:
                import time
                router_start = time.perf_counter()
                yield from self._router.chat_stream(
                    managed_messages,
                    task_type=self._task_type_for_message(message),
                    explicit_provider=explicit_provider,
                    explicit_model=explicit_model,
                    context={"correlation_id": correlation_id},
                )
                router_end = time.perf_counter()
                router_duration = (router_end - router_start) * 1000
                log.info(f"[TIMING] Router Chat Stream: {router_duration:.2f}ms")
                return
            except RuntimeError as error:
                if "available" in str(error).lower() or "unavailable" in str(error).lower():
                    try:
                        from services.local_model_service import runtime as local_model_runtime

                        local_model_runtime.start_if_installed()
                        availability = self._router.provider_availability("sentinel_local", refresh=True)
                        if availability.available:
                            yield from self._router.chat_stream(
                                managed_messages,
                                task_type=self._task_type_for_message(message),
                                context={"correlation_id": correlation_id},
                            )
                            return
                    except Exception:
                        log.debug("Streaming local recovery unavailable", exc_info=True)
                log.warning("Advanced streaming unavailable; using core conversation: %s", error)
            except Exception:
                log.exception("Advanced streaming failed; using core conversation")

        core = self._conversation.respond(request).to_dict()
        requested_provider = explicit_provider or cfg.get("provider") or "sentinel_local"
        requested_model = explicit_model or cfg.get("model") or self._get_default_model(requested_provider)
        yield {
            "type": "meta",
            "provider": "sentinel_core",
            "model": "core",
            "requested_provider": requested_provider,
            "requested_model": requested_model,
            "actual_provider": "sentinel_core",
            "actual_model": "core",
            "strategy": "core_fallback",
            "fallback_required": True,
            "fallback_reason": "all_providers_failed",
            "route": "conversation",
            "correlation_id": correlation_id,
        }
        yield {"type": "delta", "text": core["response"]}
        yield {"type": "done"}

    def analyze_metrics(self, metrics: dict) -> dict:
        cfg = self.repo.load()
        messages = [
            {"role": "system", "content": ANALYZE_PROMPT},
            {"role": "user", "content": f"Current system metrics:\n{metrics}"},
        ]

        if self._router:
            try:
                result = self._router.chat(messages, task_type=TaskType.ANALYSIS)
                return {"analysis": result["response"], "provider": result.get("provider")}
            except RuntimeError as e:
                log.error("All AI providers failed for analysis: %s", e)
                core = self._conversation.respond(ConversationRequest(message="system status", purpose="analysis"))
                return {"analysis": core.text, "conversation_mode": core.mode.value}

        raise RuntimeError("AI router not configured; direct provider calls are disabled")

    def get_free_providers(self) -> dict:
        from sentinel.core.model_router import PROVIDER_URLS

        return dict(PROVIDER_URLS)

    def _task_type_for_message(self, message: str) -> TaskType:
        analysis_keywords = ["analyze", "analyze", "metrics", "trend", "compare", "diagnose"]
        code_keywords = ["code", "write", "function", "script", "implement", "debug"]
        if any(kw in message.lower() for kw in analysis_keywords):
            return TaskType.ANALYSIS
        if any(kw in message.lower() for kw in code_keywords):
            return TaskType.CODE
        # Most conversational and learning prompts do not benefit from a long
        # hidden reasoning phase. Reserve it for explicitly complex or very
        # long requests so hosted models can start answering promptly.
        if len(message) < 240:
            return TaskType.QUICK
        return TaskType.REASONING

    @staticmethod
    def _get_default_model(provider: str) -> str:
        from sentinel.core.model_router import BUILTIN_PROVIDERS

        for p in BUILTIN_PROVIDERS:
            if p.id == provider:
                return p.default_model
        return "gpt-4o"

class _RuntimeCapabilities:
    def __init__(self, service: AIService):
        self._service = service

    def snapshot(self) -> dict:
        available = []
        router = self._service._router
        if router is not None:
            try:
                status = router.availability_snapshot()
                available = [provider_id for provider_id, value in status.items() if value.get("available")]
            except Exception:
                log.debug("Model capability probe unavailable", exc_info=True)

        registered = []
        registry = self._service._capability_registry
        if registry is not None:
            try:
                registered = registry.list_all()
            except Exception:
                log.debug("System capability probe unavailable", exc_info=True)
        categories = sorted({item.category for item in registered})
        return {
            "models": {
                "available": bool(available),
                "available_count": len(available),
                "providers": available,
            },
            "system": {
                "registered_count": len(registered),
                "categories": categories,
            },
        }
