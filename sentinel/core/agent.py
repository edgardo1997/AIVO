from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)

_COMPLEX_KEYWORDS = [
    "design",
    "architect",
    "analyze",
    "compare",
    "optimize",
    "refactor",
    "explain",
    "architect",
    "strategy",
    "complex",
    "detailed",
    "comprehensive",
    "research",
    "investigate",
    "evaluate",
    "synthesize",
    "debug",
    "troubleshoot",
]


class AgentStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class AgentSpec:
    id: str
    name: str
    description: str = ""
    provider: str = "ollama"
    model: str = ""
    capabilities: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    system_prompt: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    status: AgentStatus = AgentStatus.IDLE
    max_concurrency: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
            "model": self.model,
            "capabilities": self.capabilities,
            "allowed_tools": self.allowed_tools,
            "system_prompt": self.system_prompt,
            "config": self.config,
            "status": self.status.value,
            "max_concurrency": self.max_concurrency,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AgentSpec":
        status_str = data.get("status", "idle")
        try:
            status = AgentStatus(status_str)
        except ValueError:
            status = AgentStatus.IDLE
        return AgentSpec(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            provider=data.get("provider", "ollama"),
            model=data.get("model", ""),
            capabilities=data.get("capabilities", []),
            allowed_tools=data.get("allowed_tools", []),
            system_prompt=data.get("system_prompt", ""),
            config=data.get("config", {}),
            status=status,
            max_concurrency=data.get("max_concurrency", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class AgentRegistry:
    def __init__(self, repository: Optional[Any] = None):
        self._agents: Dict[str, AgentSpec] = {}
        self._model_router = None
        self._repository = repository

    def set_model_router(self, router: Any) -> None:
        self._model_router = router

    def set_repository(self, repo: Any) -> None:
        self._repository = repo

    def load_from_db(self) -> int:
        if not self._repository:
            return 0
        try:
            agents = self._repository.list()
            for a in agents:
                self._agents[a.id] = a
            logger.info("Loaded %d agents from database", len(agents))
            return len(agents)
        except Exception as e:
            logger.warning("Failed to load agents from database: %s", e)
            return 0

    @staticmethod
    def _analyze_complexity(task: str) -> str:
        if not task:
            return "simple"
        word_count = len(task.split())
        if word_count >= 8:
            return "complex"
        task_lower = task.lower()
        for kw in _COMPLEX_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", task_lower):
                return "complex"
        return "simple"

    def find_best_agent(
        self,
        task: str,
        strategy: str = "auto",
        capabilities_hint: Optional[List[str]] = None,
    ) -> Optional[AgentSpec]:
        candidates = [a for a in self._agents.values() if a.status != AgentStatus.DISABLED]
        if not candidates:
            return None

        if capabilities_hint:
            matched = [a for a in candidates if any(c in a.capabilities for c in capabilities_hint)]
            if matched:
                candidates = matched

        complexity = self._analyze_complexity(task)

        if strategy == "local":
            prefer_local = True
        elif strategy == "powerful":
            prefer_local = False
        else:
            prefer_local = complexity == "simple"

        def score(agent: AgentSpec) -> int:
            s = 0
            if agent.status == AgentStatus.ACTIVE:
                s += 10
            elif agent.status == AgentStatus.IDLE:
                s += 5
            is_local = agent.provider in ("ollama",)
            if prefer_local and is_local:
                s += 3
            elif not prefer_local and not is_local:
                s += 3
            return s

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    def resolve_agent(
        self,
        agent_id: Optional[str] = None,
        task: str = "",
        strategy: str = "auto",
        capabilities_hint: Optional[List[str]] = None,
    ) -> AgentSpec:
        if agent_id:
            agent = self.get(agent_id)
            if not agent:
                raise KeyError(f"Agent '{agent_id}' not found")
            return agent

        best = self.find_best_agent(task, strategy, capabilities_hint)
        if best:
            logger.info(
                "Auto-selected agent '%s' (provider=%s, model=%s) for strategy=%s task='%s'",
                best.id,
                best.provider,
                best.model,
                strategy,
                task[:60],
            )
            return best

        if self._model_router:
            from sentinel.core.model_router import TaskType, BUILTIN_PROVIDERS

            complexity = self._analyze_complexity(task)
            task_type = TaskType.QUICK if complexity == "simple" else TaskType.REASONING
            provider = self._model_router.select(task_type, context={})
            return AgentSpec(
                id=f"__auto_{provider.provider_id}",
                name=f"Auto {provider.provider_id}",
                provider=provider.provider_id,
                model=provider.model,
                capabilities=[],
                system_prompt="",
                status=AgentStatus.ACTIVE,
            )

        raise KeyError("No available agents and no ModelRouter configured")

    def execute_agent(
        self,
        agent_id: str,
        task: str,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        agent = self.get(agent_id)
        if not agent:
            raise KeyError(f"Agent '{agent_id}' not found")

        if not self._model_router:
            return {
                "agent_id": agent_id,
                "agent_name": agent.name,
                "provider": agent.provider,
                "model": agent.model,
                "task": task,
                "context": task_context or {},
                "delegated": True,
                "stub": True,
            }

        messages: List[Dict[str, str]] = []
        if agent.system_prompt:
            messages.append({"role": "system", "content": agent.system_prompt})
        user_content = task
        if task_context:
            context_str = json.dumps(task_context, indent=2)
            user_content = f"{task}\n\nContext:\n{context_str}"
        messages.append({"role": "user", "content": user_content})

        try:
            result = self._model_router.chat_with_provider(
                messages,
                agent.provider,
                agent.model,
            )
            return {
                "agent_id": agent_id,
                "agent_name": agent.name,
                "provider": result.get("provider", agent.provider),
                "model": result.get("model", agent.model),
                "task": task,
                "context": task_context or {},
                "response": result.get("response", ""),
                "delegated": True,
            }
        except Exception as e:
            logger.error("Agent '%s' execution failed: %s", agent_id, e)
            return {
                "agent_id": agent_id,
                "agent_name": agent.name,
                "provider": agent.provider,
                "model": agent.model,
                "task": task,
                "context": task_context or {},
                "delegated": True,
                "error": str(e),
            }

    def register(self, agent: AgentSpec, persist: bool = True) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not agent.created_at:
            agent.created_at = now
        agent.updated_at = now
        self._agents[agent.id] = deepcopy(agent)
        if persist and self._repository:
            try:
                self._repository.create(agent)
            except ValueError:
                self._repository.update(agent.id, agent.to_dict())

    def unregister(self, agent_id: str, persist: bool = True) -> None:
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        del self._agents[agent_id]
        if persist and self._repository:
            self._repository.delete(agent_id)

    def get(self, agent_id: str) -> Optional[AgentSpec]:
        return self._agents.get(agent_id)

    def list_all(self) -> List[AgentSpec]:
        return list(self._agents.values())

    def find_by_capability(self, capability: str) -> List[AgentSpec]:
        return [a for a in self._agents.values() if capability in a.capabilities]

    def find_by_provider(self, provider: str) -> List[AgentSpec]:
        return [a for a in self._agents.values() if a.provider == provider]

    def list_active(self) -> List[AgentSpec]:
        return [a for a in self._agents.values() if a.status == AgentStatus.ACTIVE]

    def update(self, agent_id: str, persist: bool = True, **updates: Any) -> AgentSpec:
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent '{agent_id}' not found")
        for key, value in updates.items():
            if key == "status" and isinstance(value, str):
                try:
                    value = AgentStatus(value)
                except ValueError:
                    continue
            if hasattr(agent, key):
                setattr(agent, key, value)
        agent.updated_at = datetime.now(timezone.utc).isoformat()
        if persist and self._repository:
            self._repository.update(agent_id, updates)
        return agent

    def set_delegate_fn(self, agent_id: str, fn: Callable) -> None:
        pass  # placeholder for future execution delegation

    def count(self) -> int:
        return len(self._agents)
