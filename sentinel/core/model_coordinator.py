from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import asyncio
import logging

logger = logging.getLogger(__name__)


TASK_DECOMPOSITION_RULES: Dict[str, List[Dict[str, Any]]] = {
    "project_analysis": [
        {"name": "architecture_review", "capabilities": ["reasoning"], "description": "Analyze project structure, modules, and dependencies"},
        {"name": "security_review", "capabilities": ["reasoning"], "description": "Analyze vulnerabilities, permissions, and risks"},
        {"name": "code_review", "capabilities": ["coding", "reasoning"], "description": "Analyze code quality, errors, and patterns"},
    ],
    "code_review_deep": [
        {"name": "code_quality", "capabilities": ["coding", "reasoning"], "description": "Assess code style, patterns, and best practices"},
        {"name": "error_analysis", "capabilities": ["reasoning"], "description": "Find potential bugs and error-prone patterns"},
    ],
    "security_audit": [
        {"name": "dependency_check", "capabilities": ["reasoning"], "description": "Review dependencies for known vulnerabilities"},
        {"name": "permission_audit", "capabilities": ["reasoning"], "description": "Review permission model and access controls"},
        {"name": "data_safety", "capabilities": ["reasoning"], "description": "Review data handling and privacy"},
    ],
    "research": [
        {"name": "fact_checking", "capabilities": ["reasoning"], "description": "Verify claims and facts"},
        {"name": "deep_analysis", "capabilities": ["reasoning"], "description": "Provide detailed analysis of findings"},
    ],
}


@dataclass
class ModelTask:
    task_id: str = ""
    name: str = ""
    objective: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    preferred_model: str = ""
    preferred_provider: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "objective": self.objective,
            "required_capabilities": list(self.required_capabilities),
            "preferred_model": self.preferred_model,
            "preferred_provider": self.preferred_provider,
            "dependencies": list(self.dependencies),
            "priority": self.priority,
        }


class ExecutionStrategy(Enum):
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    MIXED = "mixed"


@dataclass
class MultiModelPlan:
    tasks: List[ModelTask] = field(default_factory=list)
    execution_strategy: ExecutionStrategy = ExecutionStrategy.PARALLEL
    dependencies: List[str] = field(default_factory=list)

    def add_task(self, task: ModelTask) -> None:
        self.tasks.append(task)

    def has_dependencies(self) -> bool:
        return any(t.dependencies for t in self.tasks)

    def independent_tasks(self) -> List[ModelTask]:
        return [t for t in self.tasks if not t.dependencies]

    def dependent_tasks(self) -> List[ModelTask]:
        return [t for t in self.tasks if t.dependencies]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tasks": [t.to_dict() for t in self.tasks],
            "execution_strategy": self.execution_strategy.value,
            "task_count": len(self.tasks),
            "has_dependencies": self.has_dependencies(),
        }


@dataclass
class ModelTaskResult:
    task_id: str = ""
    task_name: str = ""
    model_id: str = ""
    provider: str = ""
    response: str = ""
    success: bool = True
    error: str = ""
    duration_ms: float = 0.0
    token_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "model_id": self.model_id,
            "provider": self.provider,
            "success": self.success,
            "error": self.error if not self.success else "",
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "response_preview": self.response[:200] if self.response else "",
        }


@dataclass
class MultiModelResult:
    results: List[ModelTaskResult] = field(default_factory=list)
    total_tasks: int = 0
    successful: int = 0
    failed: int = 0
    duration_ms: float = 0.0

    @property
    def all_successful(self) -> bool:
        return self.failed == 0

    @property
    def partial_completion(self) -> bool:
        return 0 < self.successful < self.total_tasks

    @property
    def all_failed(self) -> bool:
        return self.successful == 0 and self.total_tasks > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "successful": self.successful,
            "failed": self.failed,
            "partial_completion": self.partial_completion,
            "all_failed": self.all_failed,
            "duration_ms": self.duration_ms,
            "results": [r.to_dict() for r in self.results],
        }


class ModelCoordinator:
    def __init__(
        self,
        model_registry: Any = None,
        model_router: Any = None,
        decomposition_rules: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ):
        self._model_registry = model_registry
        self._model_router = model_router
        self._rules = decomposition_rules or TASK_DECOMPOSITION_RULES

    def set_model_registry(self, registry: Any) -> None:
        self._model_registry = registry

    def set_model_router(self, router: Any) -> None:
        self._model_router = router

    def can_coordinate(self, classified_intent: Any) -> bool:
        intent_str = self._intent_to_str(classified_intent)
        if intent_str in ("REASONING", "CODING", "ANALYSIS"):
            return True
        if intent_str == "ACTION":
            return False
        return False

    def decompose(
        self,
        user_message: str,
        classified_intent: Any = None,
        capabilities: Optional[List[str]] = None,
    ) -> MultiModelPlan:
        intent_str = self._intent_to_str(classified_intent)
        message_lower = user_message.lower()

        matched_rules: List[str] = []

        if "project" in message_lower or "aplicación" in message_lower or "app" in message_lower:
            if any(c in (capabilities or []) for c in ["coding", "reasoning"]):
                matched_rules.append("project_analysis")
            else:
                matched_rules.append("code_review_deep")
        if "seguridad" in message_lower or "security" in message_lower or "vulnerabilidad" in message_lower:
            matched_rules.append("security_audit")
        if "investiga" in message_lower or "research" in message_lower or "analiza" in message_lower:
            if "project_analysis" not in matched_rules and "code_review_deep" not in matched_rules:
                matched_rules.append("research")
        if intent_str in ("REASONING", "ANALYSIS") and not matched_rules:
            if capabilities and "coding" in capabilities:
                matched_rules.append("project_analysis")
            else:
                matched_rules.append("research")

        if not matched_rules:
            matched_rules.append("research")

        seen_names: Set[str] = set()
        tasks: List[ModelTask] = []
        for rule_name in matched_rules:
            rule_tasks = self._rules.get(rule_name, [])
            for rt in rule_tasks:
                name = rt["name"]
                if name not in seen_names:
                    seen_names.add(name)
                    task = ModelTask(
                        task_id=f"{rule_name}.{name}",
                        name=name,
                        objective=rt.get("description", name),
                        required_capabilities=list(rt.get("capabilities", [])),
                        context={"rule": rule_name, "user_message": user_message},
                    )
                    tasks.append(task)

        strategy = ExecutionStrategy.PARALLEL
        return MultiModelPlan(tasks=tasks, execution_strategy=strategy)

    def select_specialist(self, task: ModelTask) -> Optional[Any]:
        if not self._model_registry:
            logger.warning("No ModelRegistry configured for specialist selection")
            return None
        if not task.required_capabilities:
            candidates = self._model_registry.list_available()
        else:
            candidates = self._model_registry.find_candidates(task.required_capabilities)
        if not candidates:
            logger.warning(
                "No specialist candidate for task '%s' with capabilities %s",
                task.name, task.required_capabilities,
            )
            return None
        scored = []
        for m in candidates:
            score = 0
            for cap in task.required_capabilities:
                if m.has_capability(cap):
                    score += 50
            if m.speed == "fast" or m.speed == "very_fast":
                score += 5
            if m.cost == 0:
                score += 10
            if m.local:
                score += 3
            scored.append((score, m))
        scored.sort(key=lambda x: (-x[0], x[1].cost))
        best = scored[0][1]
        if best is not None:
            task.preferred_model = best.id
            task.preferred_provider = best.provider
        return best

    def assign_models(self, plan: MultiModelPlan) -> Dict[str, Optional[Any]]:
        assignments: Dict[str, Optional[Any]] = {}
        for task in plan.tasks:
            model = self.select_specialist(task)
            if model is not None:
                task.preferred_model = model.id
                task.preferred_provider = model.provider
            assignments[task.task_id] = model
        return assignments

    def build_task_prompt(self, task: ModelTask, user_message: str, context: Optional[Dict[str, Any]] = None) -> str:
        parts = [f"Objective: {task.objective}", "", f"Context: {user_message}"]
        if context:
            for key, value in context.items():
                if key != "user_message":
                    parts.append(f"{key}: {value}")
        return "\n".join(parts)

    async def execute_task(
        self,
        task: ModelTask,
        user_message: str,
        model_metadata: Any,
        chat_fn: Callable,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModelTaskResult:
        import time
        start = time.monotonic()
        try:
            prompt = self.build_task_prompt(task, user_message, context)
            messages = [
                {"role": "system", "content": f"You are a specialist in {task.name}. {task.objective}"},
                {"role": "user", "content": prompt},
            ]
            result = chat_fn(
                messages=messages,
                model_override=model_metadata.id,
            )
            elapsed = (time.monotonic() - start) * 1000
            response_text = result.get("response", "")
            usage = result.get("usage", {}) or {}
            token_count = (usage.get("prompt_tokens", 0) or 0) + (usage.get("completion_tokens", 0) or 0)
            return ModelTaskResult(
                task_id=task.task_id,
                task_name=task.name,
                model_id=model_metadata.id,
                provider=model_metadata.provider,
                response=response_text,
                success=True,
                duration_ms=elapsed,
                token_count=token_count,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning("Task '%s' failed: %s", task.name, e)
            return ModelTaskResult(
                task_id=task.task_id,
                task_name=task.name,
                model_id=model_metadata.id if model_metadata else "",
                provider=model_metadata.provider if model_metadata else "",
                success=False,
                error=str(e),
                duration_ms=elapsed,
            )

    async def execute_plan(
        self,
        plan: MultiModelPlan,
        user_message: str,
        chat_fn: Callable,
        context: Optional[Dict[str, Any]] = None,
    ) -> MultiModelResult:
        import time
        start = time.monotonic()

        assignments = self.assign_models(plan)
        results: List[ModelTaskResult] = []

        if plan.execution_strategy == ExecutionStrategy.PARALLEL and not plan.has_dependencies():
            tasks = []
            for task in plan.tasks:
                model = assignments.get(task.task_id)
                if model is None:
                    results.append(ModelTaskResult(
                        task_id=task.task_id,
                        task_name=task.name,
                        success=False,
                        error=f"No compatible model for capabilities {task.required_capabilities}",
                    ))
                    continue
                tasks.append(self.execute_task(task, user_message, model, chat_fn, context))
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in task_results:
                if isinstance(r, Exception):
                    results.append(ModelTaskResult(
                        task_id="error",
                        task_name="error",
                        success=False,
                        error=str(r),
                    ))
                else:
                    results.append(r)

        else:
            task_map = {t.task_id: t for t in plan.tasks}
            completed: Set[str] = set()
            remaining = list(plan.tasks)
            while remaining:
                batch = [t for t in remaining if all(d in completed for d in t.dependencies)]
                if not batch:
                    remaining_tasks = ", ".join(t.name for t in remaining)
                    logger.warning("Circular dependency detected for tasks: %s", remaining_tasks)
                    break
                batch_tasks = []
                for task in batch:
                    model = assignments.get(task.task_id)
                    if model is None:
                        results.append(ModelTaskResult(
                            task_id=task.task_id,
                            task_name=task.name,
                            success=False,
                            error=f"No compatible model for capabilities {task.required_capabilities}",
                        ))
                        completed.add(task.task_id)
                        continue
                    batch_tasks.append(self.execute_task(task, user_message, model, chat_fn, context))

                if batch_tasks:
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                    for r in batch_results:
                        if isinstance(r, Exception):
                            results.append(ModelTaskResult(
                                task_id="error", task_name="error",
                                success=False, error=str(r),
                            ))
                        else:
                            results.append(r)
                            completed.add(r.task_id)
                for task in batch:
                    remaining.remove(task)

        elapsed = (time.monotonic() - start) * 1000
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        return MultiModelResult(
            results=results,
            total_tasks=len(plan.tasks),
            successful=successful,
            failed=failed,
            duration_ms=elapsed,
        )

    def _intent_to_str(self, classified_intent: Any) -> str:
        if classified_intent is None:
            return ""
        cat = getattr(classified_intent, "category", None)
        if cat is None:
            if hasattr(classified_intent, "value"):
                return str(classified_intent.value)
            return str(classified_intent)
        return cat.value if hasattr(cat, "value") else str(cat)

    def get_decomposition_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self._rules)

    def add_decomposition_rule(self, name: str, tasks: List[Dict[str, Any]]) -> None:
        self._rules[name] = tasks
