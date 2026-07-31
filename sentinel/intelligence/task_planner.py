from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass
class PlannedTask:
    task_id: str = ""
    name: str = ""
    objective: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    preferred_model: str = ""
    preferred_provider: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5
    complexity: TaskComplexity = TaskComplexity.MODERATE

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
            "complexity": self.complexity.value,
        }


@dataclass
class TaskPlan:
    original_request: str = ""
    tasks: List[PlannedTask] = field(default_factory=list)
    execution_strategy: str = "parallel"
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_request": self.original_request,
            "tasks": [t.to_dict() for t in self.tasks],
            "execution_strategy": self.execution_strategy,
        }


DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "security": ["security", "vulnerability", "threat", "attack", "exploit", "permission", "access control", "authentication", "encryption", "firewall"],
    "performance": ["performance", "speed", "latency", "throughput", "bottleneck", "optimization", "scalability", "memory", "cpu", "profiling"],
    "architecture": ["architecture", "design", "pattern", "structure", "module", "component", "interface", "dependency", "layers"],
    "code_quality": ["code", "quality", "style", "lint", "refactor", "technical debt", "maintainability", "readability"],
    "testing": ["test", "testing", "coverage", "unit test", "integration test", "assertion", "mock"],
    "data": ["data", "database", "schema", "query", "storage", "index", "migration"],
    "devops": ["devops", "deployment", "ci/cd", "pipeline", "docker", "kubernetes", "infrastructure"],
    "ux": ["ux", "user experience", "usability", "accessibility", "ui", "interface", "workflow"],
}


def classify_request(user_message: str) -> Dict[str, Any]:
    msg_lower = user_message.lower()
    detected_domains = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            detected_domains.append(domain)
    if not detected_domains:
        detected_domains.append("general")
    word_count = len(msg_lower.split())
    if word_count < 10:
        complexity = TaskComplexity.SIMPLE
    elif word_count < 30:
        complexity = TaskComplexity.MODERATE
    else:
        complexity = TaskComplexity.COMPLEX
    return {"domains": detected_domains, "complexity": complexity}


DOMAIN_TASKS: Dict[str, List[Dict[str, Any]]] = {
    "security": [
        {"name": "vulnerability_analysis", "capabilities": ["reasoning"], "description": "Analyze security vulnerabilities and threats"},
        {"name": "access_review", "capabilities": ["reasoning"], "description": "Review access controls and permissions"},
    ],
    "performance": [
        {"name": "bottleneck_analysis", "capabilities": ["reasoning"], "description": "Identify performance bottlenecks and constraints"},
        {"name": "optimization_suggestions", "capabilities": ["reasoning", "coding"], "description": "Suggest performance optimizations"},
    ],
    "architecture": [
        {"name": "structure_review", "capabilities": ["reasoning"], "description": "Review architectural structure and patterns"},
        {"name": "dependency_analysis", "capabilities": ["reasoning"], "description": "Analyze module dependencies and couplings"},
    ],
    "code_quality": [
        {"name": "style_review", "capabilities": ["coding"], "description": "Review code style and conventions"},
        {"name": "pattern_analysis", "capabilities": ["reasoning", "coding"], "description": "Analyze code patterns and anti-patterns"},
    ],
    "testing": [
        {"name": "coverage_review", "capabilities": ["reasoning"], "description": "Review test coverage and gaps"},
        {"name": "test_quality", "capabilities": ["coding"], "description": "Assess test quality and effectiveness"},
    ],
    "data": [
        {"name": "schema_review", "capabilities": ["reasoning"], "description": "Review data schema and model design"},
        {"name": "query_analysis", "capabilities": ["reasoning", "coding"], "description": "Analyze query performance and correctness"},
    ],
    "devops": [
        {"name": "pipeline_review", "capabilities": ["reasoning"], "description": "Review CI/CD pipeline configuration"},
        {"name": "infrastructure_check", "capabilities": ["reasoning"], "description": "Check infrastructure setup and configuration"},
    ],
    "ux": [
        {"name": "usability_review", "capabilities": ["reasoning"], "description": "Review user experience and usability"},
        {"name": "workflow_analysis", "capabilities": ["reasoning"], "description": "Analyze user workflows and interactions"},
    ],
    "general": [
        {"name": "analysis", "capabilities": ["reasoning"], "description": "General analysis of the request"},
    ],
}


class TaskPlanner:
    def __init__(self, decomposition_rules: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self._rules = decomposition_rules or DOMAIN_TASKS

    def plan(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> TaskPlan:
        classification = classify_request(user_message)
        complexity = classification["complexity"]
        domains = classification["domains"]
        if complexity == TaskComplexity.SIMPLE:
            tasks = [self._build_single_task(user_message, domains)]
        else:
            tasks = self._build_multi_task(user_message, domains, complexity)
        strategy = "parallel" if complexity != TaskComplexity.SIMPLE else "sequential"
        return TaskPlan(original_request=user_message, tasks=tasks, execution_strategy=strategy, context=context or {})

    def _build_single_task(self, user_message: str, domains: List[str]) -> PlannedTask:
        domain = domains[0]
        return PlannedTask(
            task_id="task_1",
            name="analysis",
            objective=user_message,
            required_capabilities=["reasoning"],
            priority=5,
            complexity=TaskComplexity.SIMPLE,
        )

    def _build_multi_task(self, user_message: str, domains: List[str], complexity: TaskComplexity) -> List[PlannedTask]:
        tasks: List[PlannedTask] = []
        seen = set()
        task_id = 1
        for domain in domains:
            if domain not in self._rules:
                continue
            for rule in self._rules[domain]:
                name = rule["name"]
                if name in seen:
                    continue
                seen.add(name)
                caps = list(rule.get("capabilities", ["reasoning"]))
                tasks.append(PlannedTask(
                    task_id=f"task_{task_id}",
                    name=name,
                    objective=f"{rule['description']}: {user_message}",
                    required_capabilities=caps,
                    priority=len(domains) - domains.index(domain),
                    complexity=complexity,
                ))
                task_id += 1
        if not tasks:
            tasks.append(self._build_single_task(user_message, domains))
        return tasks

    def add_rule(self, domain: str, tasks: List[Dict[str, Any]]) -> None:
        if domain not in self._rules:
            self._rules[domain] = []
        self._rules[domain].extend(tasks)
