from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SkillSpec:
    id: str
    name: str
    description: str
    category: str
    tools: List[str] = field(default_factory=list)
    system_prompt: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    risk_level: str = "low"
    requires_confirmation: bool = False
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tools": list(self.tools),
            "system_prompt": self.system_prompt,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "version": self.version,
            "tags": list(self.tags),
        }


@dataclass
class SkillResult:
    skill_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    plan_summary: str = ""
    duration_ms: float = 0.0
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "plan_summary": self.plan_summary,
            "duration_ms": self.duration_ms,
            "tool_results": self.tool_results,
        }


BUILTIN_SKILLS: List[SkillSpec] = [
    SkillSpec(
        id="code.review",
        name="Code Review",
        description="Analyze source code for bugs, security issues, style problems, and improvement suggestions",
        category="code",
        tools=["filesystem.read", "executor.command"],
        system_prompt="You are a senior code reviewer. Analyze the provided code for: 1) Bugs and logic errors, 2) Security vulnerabilities, 3) Performance issues, 4) Code style and maintainability, 5) Missing error handling. Provide specific line references and concrete fix suggestions.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory path to review"},
                "language": {"type": "string", "description": "Programming language (auto-detected if not specified)"},
                "depth": {"type": "string", "enum": ["quick", "deep"], "default": "quick"},
            },
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "issues": {"type": "array"},
                "suggestions": {"type": "array"},
            },
        },
        preconditions=["File or directory must exist and be readable"],
        postconditions=["Code issues are identified and reported"],
        risk_level="low",
        tags=["code", "review", "quality"],
    ),
    SkillSpec(
        id="system.diagnose",
        name="System Diagnosis",
        description="Run a comprehensive system health check including CPU, memory, disk, network, and processes",
        category="system",
        tools=["system.cpu", "system.info", "system.processes", "system.gpu"],
        system_prompt="You are a system diagnostic expert. Analyze the collected system metrics and provide: 1) Overall health assessment, 2) Resource bottleneck identification, 3) Specific recommendations for optimization, 4) Warning signs that need attention. Be concise and actionable.",
        input_schema={
            "type": "object",
            "properties": {
                "include_gpu": {"type": "boolean", "default": False},
                "process_limit": {"type": "integer", "default": 10},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "health_score": {"type": "number"},
                "bottlenecks": {"type": "array"},
                "recommendations": {"type": "array"},
            },
        },
        postconditions=["System health is assessed and reported"],
        risk_level="low",
        tags=["system", "diagnose", "health"],
    ),
    SkillSpec(
        id="files.organize",
        name="File Organizer",
        description="Analyze and organize files in a directory by type, date, or custom rules",
        category="files",
        tools=["filesystem.read", "filesystem.write", "executor.command"],
        system_prompt="You are a file organization assistant. Analyze the files in the given directory and suggest or execute an organization strategy. Consider: 1) File types and extensions, 2) Creation/modification dates, 3) File sizes, 4) Naming conventions. Provide a clear summary of what was done or what will be done.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to organize"},
                "mode": {"type": "string", "enum": ["analyze", "dry-run", "execute"], "default": "analyze"},
                "strategy": {"type": "string", "enum": ["by_type", "by_date", "by_size"], "default": "by_type"},
            },
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "files_analyzed": {"type": "integer"},
                "actions": {"type": "array"},
            },
        },
        preconditions=["Directory must exist and be readable"],
        postconditions=["Files are organized according to the chosen strategy"],
        risk_level="medium",
        requires_confirmation=True,
        tags=["files", "organize", "cleanup"],
    ),
    SkillSpec(
        id="research.summarize",
        name="Research & Summarize",
        description="Research a topic by gathering information from multiple sources and producing a structured summary",
        category="research",
        tools=["ai.chat"],
        system_prompt="You are a research assistant. Given a topic, gather relevant information and produce a structured summary with: 1) Key findings, 2) Supporting evidence, 3) Contradicting viewpoints, 4) Conclusions and recommendations. Cite sources where possible.",
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to research"},
                "depth": {"type": "string", "enum": ["brief", "detailed"], "default": "brief"},
                "format": {"type": "string", "enum": ["bullets", "report", "presentation"], "default": "bullets"},
            },
            "required": ["topic"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "key_findings": {"type": "array"},
                "sources": {"type": "array"},
            },
        },
        risk_level="low",
        tags=["research", "summarize", "information"],
    ),
    SkillSpec(
        id="data.analyze",
        name="Data Analysis",
        description="Analyze structured data (CSV, JSON) to find patterns, trends, anomalies, and generate insights",
        category="data",
        tools=["filesystem.read", "executor.command"],
        system_prompt="You are a data analyst. Analyze the provided data and produce: 1) Dataset overview (rows, columns, types), 2) Key statistics (mean, median, min, max, stddev for numeric columns), 3) Trends and patterns, 4) Anomalies and outliers, 5) Actionable insights and recommendations.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to data file (CSV or JSON)"},
                "analysis_type": {
                    "type": "string",
                    "enum": ["overview", "stats", "trends", "anomalies", "full"],
                    "default": "full",
                },
            },
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "overview": {"type": "object"},
                "statistics": {"type": "object"},
                "insights": {"type": "array"},
            },
        },
        preconditions=["Data file must exist and be readable"],
        postconditions=["Data is analyzed and insights are generated"],
        risk_level="low",
        tags=["data", "analyze", "insights"],
    ),
]


class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, SkillSpec] = {}

    def register(self, skill: SkillSpec) -> None:
        if skill.id in self._skills:
            raise ValueError(f"Skill '{skill.id}' already registered")
        self._skills[skill.id] = skill
        logger.info("Skill registered: %s v%s (%s)", skill.id, skill.version, skill.category)

    def unregister(self, skill_id: str) -> Optional[SkillSpec]:
        return self._skills.pop(skill_id, None)

    def get(self, skill_id: str) -> Optional[SkillSpec]:
        return self._skills.get(skill_id)

    def list(self, category: Optional[str] = None) -> List[SkillSpec]:
        if category:
            return [s for s in self._skills.values() if s.category == category]
        return list(self._skills.values())

    def find(self, query: str) -> List[SkillSpec]:
        q = query.lower()
        results = []
        for s in self._skills.values():
            if q in s.name.lower() or q in s.description.lower() or q in s.id.lower():
                results.append(s)
                continue
            for tag in s.tags:
                if q in tag.lower():
                    results.append(s)
                    break
        return results

    def find_for_task(self, task: str) -> List[SkillSpec]:
        q = task.lower()
        keywords = set(q.split())
        scored = []
        for s in self._skills.values():
            score = 0
            for tag in s.tags:
                if tag.lower() in q:
                    score += 3
            for kw in s.name.lower().split("_"):
                if kw in keywords:
                    score += 2
            for kw in s.description.lower().split():
                if kw in keywords:
                    score += 1
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored]

    def load_builtins(self) -> int:
        count = 0
        for skill in BUILTIN_SKILLS:
            if skill.id not in self._skills:
                self._skills[skill.id] = skill
                count += 1
        logger.info("Loaded %d built-in skills", count)
        return count

    def to_dict(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._skills.values()]
