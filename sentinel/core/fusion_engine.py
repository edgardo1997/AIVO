from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


@dataclass
class FusionFinding:
    source_task: str = ""
    source_model: str = ""
    category: str = ""
    summary: str = ""
    detail: str = ""
    severity: str = "info"

    def to_dict(self) -> Dict[str, str]:
        return {
            "source_task": self.source_task,
            "source_model": self.source_model,
            "category": self.category,
            "summary": self.summary,
            "detail": self.detail[:500] if self.detail else "",
            "severity": self.severity,
        }


@dataclass
class FusionConflict:
    category: str = ""
    finding_a: str = ""
    finding_b: str = ""
    source_a: str = ""
    source_b: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "category": self.category,
            "finding_a": self.finding_a[:200],
            "finding_b": self.finding_b[:200],
            "source_a": self.source_a,
            "source_b": self.source_b,
            "description": self.description,
        }


@dataclass
class FusionResult:
    summary: str = ""
    findings: List[FusionFinding] = field(default_factory=list)
    conflicts: List[FusionConflict] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    has_conflicts: bool = False

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "categories": list(self.categories),
            "sources": list(self.sources),
            "finding_count": self.finding_count,
            "has_conflicts": self.has_conflicts,
            "findings": [f.to_dict() for f in self.findings],
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


class FusionEngine:
    def __init__(self):
        self._category_keywords: Dict[str, List[str]] = {
            "architecture": ["architecture", "structure", "module", "dependency", "component", "pattern"],
            "security": ["security", "vulnerability", "risk", "permission", "access", "threat", "attack"],
            "code_quality": ["code", "quality", "style", "lint", "error", "bug", "refactor"],
            "performance": ["performance", "speed", "latency", "throughput", "optimization"],
            "testing": ["test", "coverage", "assertion", "mock", "integration"],
            "documentation": ["documentation", "docstring", "readme", "comment"],
        }

    def fuse(self, results: List[Any]) -> FusionResult:
        if not results:
            return FusionResult(summary="No results to analyze.")

        findings: List[FusionFinding] = []
        seen_summaries: Set[str] = set()

        for result in results:
            task_name = getattr(result, "task_name", "unknown")
            model_id = getattr(result, "model_id", "unknown")
            response = getattr(result, "response", "")
            if not result.success:
                findings.append(FusionFinding(
                    source_task=task_name,
                    source_model=model_id,
                    category="error",
                    summary=f"{task_name}: failed",
                    detail=getattr(result, "error", "Unknown error"),
                    severity="error",
                ))
                continue

            paragraphs = self._split_paragraphs(response)
            for para in paragraphs:
                category = self._classify(para)
                dedup_key = f"{category}:{para[:100]}"
                if dedup_key in seen_summaries:
                    continue
                seen_summaries.add(dedup_key)
                summary = para[:150].replace("\n", " ")
                findings.append(FusionFinding(
                    source_task=task_name,
                    source_model=model_id,
                    category=category,
                    summary=summary,
                    detail=para,
                    severity=self._assess_severity(para, category),
                ))

        sources = list(dict.fromkeys(
            f"{r.task_name} ({r.model_id})" for r in results
        ))
        categories = list(dict.fromkeys(f.category for f in findings))

        conflicts = self._detect_conflicts(findings)
        summary = self._build_summary(results, findings, conflicts, categories)

        return FusionResult(
            summary=summary,
            findings=self._order_findings(findings),
            conflicts=conflicts,
            categories=categories,
            sources=sources,
            has_conflicts=len(conflicts) > 0,
        )

    def _classify(self, text: str) -> str:
        text_lower = text.lower()
        best_category = "general"
        best_score = 0
        for category, keywords in self._category_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_category = category
        return best_category

    def _assess_severity(self, text: str, category: str) -> str:
        text_lower = text.lower()
        critical_words = ["critical", "high risk", "severe", "dangerous", "exploit", "vulnerability"]
        warning_words = ["warning", "caution", "should", "recommend", "could", "might", "potential"]
        for w in critical_words:
            if w in text_lower:
                return "critical"
        for w in warning_words:
            if w in text_lower:
                return "warning"
        return "info"

    def _detect_conflicts(self, findings: List[FusionFinding]) -> List[FusionConflict]:
        conflicts: List[FusionConflict] = []
        for i in range(len(findings)):
            for j in range(i + 1, len(findings)):
                if findings[i].source_task == findings[j].source_task:
                    continue
                if findings[i].category != findings[j].category:
                    continue
                if findings[i].severity == findings[j].severity:
                    continue
                if self._is_contradictory(findings[i].detail, findings[j].detail):
                    conflicts.append(FusionConflict(
                        category=findings[i].category,
                        finding_a=findings[i].summary,
                        finding_b=findings[j].summary,
                        source_a=findings[i].source_task,
                        source_b=findings[j].source_task,
                        description=f"Discrepancy between {findings[i].source_task} and {findings[j].source_task} "
                                    f"in category '{findings[i].category}'. Requires human review.",
                    ))
        return conflicts

    def _is_contradictory(self, text_a: str, text_b: str) -> bool:
        text_a_lower = text_a.lower()
        text_b_lower = text_b.lower()
        negations = ["no ", "not ", "none", "without", "lacks", "missing", "absent"]
        positives = ["found", "detected", "present", "exists", "has ", "contains"]
        a_has_negation = any(n in text_a_lower for n in negations)
        b_has_negation = any(n in text_b_lower for n in negations)
        a_has_positive = any(p in text_a_lower for p in positives)
        b_has_positive = any(p in text_b_lower for p in positives)
        if (a_has_negation and b_has_positive) or (a_has_positive and b_has_negation):
            return True
        return False

    def _order_findings(self, findings: List[FusionFinding]) -> List[FusionFinding]:
        severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        return sorted(findings, key=lambda f: (
            severity_order.get(f.severity, 99),
            f.category,
        ))

    def _split_paragraphs(self, text: str) -> List[str]:
        paragraphs = []
        current = []
        for line in text.split("\n"):
            line = line.strip()
            if not line and current:
                paragraphs.append("\n".join(current))
                current = []
            elif line:
                current.append(line)
        if current:
            paragraphs.append("\n".join(current))
        return [p for p in paragraphs if len(p) > 20]

    def _build_summary(
        self,
        results: List[Any],
        findings: List[FusionFinding],
        conflicts: List[FusionConflict],
        categories: List[str],
    ) -> str:
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        parts = [f"Analysis complete: {successful}/{total} tasks completed."]
        if categories:
            parts.append(f"Categories analyzed: {', '.join(categories)}.")
        if failed > 0:
            parts.append(f"{failed} task(s) encountered errors.")
        critical = [f for f in findings if f.severity == "critical"]
        if critical:
            parts.append(f"Critical findings: {len(critical)}.")
        if conflicts:
            parts.append(f"Conflicts detected: {len(conflicts)} (requires human review).")
        return " ".join(parts)

    def find_by_category(self, result: FusionResult, category: str) -> List[FusionFinding]:
        return [f for f in result.findings if f.category == category]
