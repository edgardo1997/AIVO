"""Multi-agent orchestration: decomposes complex tasks into sub-tasks,
assigns each to the best-suited agent, and merges results.

This is Sentinel's "coordinate multiple intelligences" capability.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .agent import AgentRegistry, AgentSpec, AgentStatus

log = logging.getLogger("sentinel.multi_agent")

_COMPLEX_KEYWORDS = [
    "design",
    "architect",
    "analyze",
    "compare",
    "optimize",
    "refactor",
    "investigate",
    "evaluate",
    "synthesize",
    "debug",
    "troubleshoot",
    "plan",
    "strategy",
    "overview",
    "research",
    "comprehensive",
]

_MULTI_STEP_PATTERNS = [
    r"\b(first|then|next|finally|after|before)\b",
    r"\b(step\s*\d|phase|stage|part)\b",
    r"\band\s+also\b",
    r"\b(compare|contrast|difference)\b",
]


@dataclass
class SubTask:
    id: str
    description: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    dependencies: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    agent_id: Optional[str] = None
    agent_strategy: str = "auto"


@dataclass
class SubTaskResult:
    sub_task_id: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    agent_id: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class DecompositionResult:
    sub_tasks: List[SubTask]
    decomposition_method: str = "rule"


@dataclass
class MultiAgentResult:
    success: bool
    sub_task_results: List[SubTaskResult]
    merged_output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    total_duration_ms: float = 0.0


class MultiAgentOrchestrator:
    """Decomposes complex tasks, delegates to agents, and merges results."""

    def __init__(
        self,
        agent_registry: Optional[AgentRegistry] = None,
        decompose_fn: Optional[Callable[[str, Dict[str, Any]], DecompositionResult]] = None,
        execute_agent_fn: Optional[Callable[[str, str, Dict[str, Any]], Dict[str, Any]]] = None,
        merge_fn: Optional[Callable[[str, List[SubTaskResult]], Dict[str, Any]]] = None,
    ):
        self._registry = agent_registry
        self._decompose_fn = decompose_fn or self._default_decompose
        self._execute_agent = execute_agent_fn
        self._merge_fn = merge_fn or self._default_merge

    def set_agent_registry(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def set_execute_agent_fn(self, fn: Callable[[str, str, Dict[str, Any]], Dict[str, Any]]) -> None:
        self._execute_agent = fn

    def _is_complex(self, task: str) -> bool:
        if not task:
            return False
        word_count = len(task.split())
        if word_count >= 15:
            return True
        task_lower = task.lower()
        for kw in _COMPLEX_KEYWORDS:
            if kw in task_lower:
                return True
        import re

        for pattern in _MULTI_STEP_PATTERNS:
            if re.search(pattern, task_lower):
                return True
        return False

    def _default_decompose(self, task: str, context: Optional[Dict[str, Any]] = None) -> DecompositionResult:
        if not self._is_complex(task):
            sub = SubTask(
                id="st_main",
                description=task,
                inputs=context or {},
                expected_output="Complete response for the task",
            )
            return DecompositionResult(sub_tasks=[sub], decomposition_method="passthrough")

        task_lower = task.lower()
        sub_tasks = []

        if "research" in task_lower or "investigate" in task_lower:
            sub_tasks.append(
                SubTask(
                    id="st_research",
                    description="Research and gather information",
                    inputs={},
                    expected_output="Gathered information and data",
                    required_capabilities=["system.read", "filesystem.read"],
                )
            )
        if "analyze" in task_lower or "evaluate" in task_lower:
            sub_tasks.append(
                SubTask(
                    id="st_analyze",
                    description="Analyze the gathered information",
                    dependencies=[s.id for s in sub_tasks] if sub_tasks else [],
                    expected_output="Analysis results and insights",
                    required_capabilities=[],
                    agent_strategy="powerful",
                )
            )
        if "design" in task_lower or "architect" in task_lower or "plan" in task_lower:
            sub_tasks.append(
                SubTask(
                    id="st_design",
                    description="Design or plan the solution",
                    dependencies=[s.id for s in sub_tasks] if sub_tasks else [],
                    expected_output="Design or plan document",
                    required_capabilities=[],
                    agent_strategy="powerful",
                )
            )
        if not sub_tasks:
            sub_tasks.append(
                SubTask(
                    id="st_main",
                    description=task,
                    inputs=context or {},
                    expected_output="Complete response for the task",
                    agent_strategy="powerful",
                )
            )

        return DecompositionResult(sub_tasks=sub_tasks, decomposition_method="rule")

    def assign_agents(self, sub_tasks: List[SubTask]) -> List[SubTask]:
        if not self._registry:
            for st in sub_tasks:
                st.agent_id = None
            return sub_tasks

        for st in sub_tasks:
            if st.agent_id:
                continue
            agent = self._registry.find_best_agent(
                st.description,
                strategy=st.agent_strategy,
                capabilities_hint=st.required_capabilities or None,
            )
            st.agent_id = agent.id if agent else None
        return sub_tasks

    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> MultiAgentResult:
        start = time.monotonic()
        context = context or {}

        decomposition = self._decompose_fn(task, context)
        sub_tasks = self.assign_agents(decomposition.sub_tasks)

        if not sub_tasks:
            return MultiAgentResult(
                success=False,
                sub_task_results=[],
                error="Task decomposition produced no sub-tasks",
            )

        if len(sub_tasks) == 1 and decomposition.decomposition_method == "passthrough":
            return await self._execute_single(sub_tasks[0], task, context, start)

        return await self._execute_multi(sub_tasks, task, context, start)

    async def _execute_single(
        self,
        sub_task: SubTask,
        task: str,
        context: Dict[str, Any],
        start: float,
    ) -> MultiAgentResult:
        result = await self._run_sub_task(sub_task, context)
        duration = (time.monotonic() - start) * 1000
        merged = self._merge_fn(task, [result])
        return MultiAgentResult(
            success=result.success,
            sub_task_results=[result],
            merged_output=merged,
            error=result.error,
            total_duration_ms=duration,
        )

    async def _execute_multi(
        self,
        sub_tasks: List[SubTask],
        task: str,
        context: Dict[str, Any],
        start: float,
    ) -> MultiAgentResult:
        completed: Dict[str, SubTaskResult] = {}
        dep_map = {st.id: set(st.dependencies) for st in sub_tasks}
        {st.id: st for st in sub_tasks}

        while len(completed) < len(sub_tasks):
            ready = [st for st in sub_tasks if st.id not in completed and not (dep_map[st.id] - set(completed.keys()))]
            if not ready:
                remaining = [st.id for st in sub_tasks if st.id not in completed]
                return MultiAgentResult(
                    success=False,
                    sub_task_results=list(completed.values()),
                    error=f"Circular dependency or stuck tasks: {remaining}",
                    total_duration_ms=(time.monotonic() - start) * 1000,
                )

            tasks = [
                self._run_sub_task(st, {**context, "completed": {k: v.data for k, v in completed.items()}})
                for st in ready
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for st, res in zip(ready, results):
                if isinstance(res, Exception):
                    completed[st.id] = SubTaskResult(
                        sub_task_id=st.id,
                        success=False,
                        error=str(res),
                    )
                else:
                    completed[st.id] = res

        all_results = list(completed.values())
        success = all(r.success for r in all_results)
        merged = self._merge_fn(task, all_results)
        duration = (time.monotonic() - start) * 1000
        error = next((r.error for r in all_results if r.error), None)
        return MultiAgentResult(
            success=success,
            sub_task_results=all_results,
            merged_output=merged,
            error=error,
            total_duration_ms=duration,
        )

    async def _run_sub_task(self, sub_task: SubTask, context: Dict[str, Any]) -> SubTaskResult:
        sub_start = time.monotonic()
        log.info("Running sub-task %s (agent=%s): %s", sub_task.id, sub_task.agent_id, sub_task.description[:80])

        if not sub_task.agent_id or not self._execute_agent:
            return SubTaskResult(
                sub_task_id=sub_task.id,
                success=True,
                data={"response": f"[passthrough] {sub_task.description}"},
                duration_ms=(time.monotonic() - sub_start) * 1000,
            )

        try:
            result = self._execute_agent(
                sub_task.agent_id,
                sub_task.description,
                sub_task.inputs or context,
            )
            duration = (time.monotonic() - sub_start) * 1000
            if result.get("error"):
                return SubTaskResult(
                    sub_task_id=sub_task.id,
                    success=False,
                    error=result["error"],
                    agent_id=sub_task.agent_id,
                    duration_ms=duration,
                )
            return SubTaskResult(
                sub_task_id=sub_task.id,
                success=True,
                data={"response": result.get("response", ""), "agent_id": sub_task.agent_id},
                agent_id=sub_task.agent_id,
                duration_ms=duration,
            )
        except Exception as e:
            log.error("Sub-task %s failed: %s", sub_task.id, e)
            return SubTaskResult(
                sub_task_id=sub_task.id,
                success=False,
                error=str(e),
                agent_id=sub_task.agent_id,
                duration_ms=(time.monotonic() - sub_start) * 1000,
            )

    @staticmethod
    def _default_merge(task: str, results: List[SubTaskResult]) -> Dict[str, Any]:
        parts = []
        for r in results:
            if r.success and r.data:
                resp = r.data.get("response", "")
                if resp:
                    parts.append(resp)
            elif r.error:
                parts.append(f"[{r.sub_task_id} error: {r.error}]")

        return {
            "task": task,
            "output": "\n\n".join(parts) if parts else "",
            "sub_task_count": len(results),
            "success_count": sum(1 for r in results if r.success),
        }
