import logging
from typing import Optional
from repositories.ai_repository import AIRepository
from sentinel.core.model_router import ModelRouter, TaskType
from sentinel.core.context_window import ContextWindowManager, count_messages_tokens

log = logging.getLogger("sentinel.ai_service")

SYSTEM_PROMPT = """You are an AI assistant integrated into AIVO, a desktop productivity tool. Your purpose is to help the user with system monitoring, file management, task execution, and general computer assistance. You have access to system resources and can execute commands on the user's machine. Be concise, accurate, and helpful. When performing actions, explain what you're doing. If a request seems dangerous (deleting files, modifying system settings), warn the user first and ask for confirmation."""

ANALYZE_PROMPT = """You are a system analysis AI. Analyze the provided metrics and identify issues, trends, and recommendations. Be specific and actionable. Format your response as bullet points covering: 1) Critical Issues, 2) Warnings, 3) Recommendations."""


class AIService:
    def __init__(self, repo: AIRepository = None, router: ModelRouter = None, context_manager: ContextWindowManager = None):
        self.repo = repo or AIRepository()
        self._router = router
        self._context_manager = context_manager or ContextWindowManager()

    def set_router(self, router: ModelRouter) -> None:
        self._router = router

    def get_config(self) -> dict:
        cfg = self.repo.load()
        provider = cfg.get("provider", "openrouter")
        model = cfg.get("model") or self._get_default_model(provider)
        return {
            "provider": provider,
            "api_key": "set" if cfg.get("api_key") else "",
            "model": model,
            "base_url": cfg.get("base_url") or "",
            "strategy": getattr(self._router, '_strategy', 'priority') if self._router else 'priority',
        }

    def set_config(self, cfg: dict) -> dict:
        current = self.repo.load()
        current.update({k: v for k, v in cfg.items() if v is not None})
        self.repo.save(current)
        if self._router and cfg.get("api_key"):
            provider = cfg.get("provider") or current.get("provider", "openrouter")
            self._router.set_api_key(provider, cfg["api_key"])
        return {"status": "saved"}

    def chat(
        self,
        message: str,
        system_prompt: str = None,
        context: list = None,
        provider: str = None,
        model_override: str = None,
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

        model = model_override or cfg.get("model") or self._get_default_model(cfg.get("provider", "openrouter"))
        managed = self._context_manager.manage(messages, model=model)
        managed_messages = managed["messages"]
        if managed["trimmed"] > 0 or managed["summarized"]:
            log.info(
                "Context window: %d→%d msgs, %d tokens, trimmed=%d summarized=%s",
                managed["original_count"], managed["final_count"],
                managed.get("total_tokens", 0), managed["trimmed"], managed["summarized"],
            )

        if self._router:
            try:
                result = self._router.chat(managed_messages, task_type=task_type)
                return {"response": result["response"], "provider": result.get("provider"), "model": result.get("model")}
            except RuntimeError as e:
                log.error("All AI providers failed: %s", e)
                raise Exception(str(e))

        try:
            client = self._make_client(cfg)
            resp = client.chat.completions.create(model=model, messages=managed_messages)
            return {"response": resp.choices[0].message.content, "provider": cfg.get("provider"), "model": model}
        except Exception as e:
            log.error("AI chat error: %s", e)
            raise

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
                raise Exception(str(e))

        model = cfg.get("model") or self._get_default_model(cfg.get("provider", "openrouter"))
        try:
            client = self._make_client(cfg)
            resp = client.chat.completions.create(model=model, messages=messages)
            return {"analysis": resp.choices[0].message.content}
        except Exception as e:
            log.error("AI analysis error: %s", e)
            raise

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
        if len(message) < 60:
            return TaskType.QUICK
        return TaskType.REASONING

    @staticmethod
    def _get_default_model(provider: str) -> str:
        from sentinel.core.model_router import BUILTIN_PROVIDERS
        for p in BUILTIN_PROVIDERS:
            if p.id == provider:
                return p.default_model
        return "gpt-4o"

    @staticmethod
    def _make_client(cfg: dict):
        from openai import OpenAI
        base_url = cfg.get("base_url") or ""
        api_key = cfg.get("api_key", "")
        if cfg.get("provider") == "ollama":
            api_key = "ollama"
        return OpenAI(base_url=base_url, api_key=api_key)
