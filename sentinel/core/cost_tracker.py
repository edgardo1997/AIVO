import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging

from .model_router import TaskType

logger = logging.getLogger(__name__)

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "openrouter": {
        "deepseek/deepseek-v4-flash:free": 0.0,
        "deepseek/deepseek-v4-flash": 0.0,
        "gpt-4o": 0.0025,
        "gpt-4o-mini": 0.00015,
        "default": 0.0,
    },
    "deepseek": {
        "deepseek-v4-flash": 0.0,
        "deepseek-reasoner": 0.0,
        "default": 0.0,
    },
    "groq": {
        "llama-3.3-70b-versatile": 0.0,
        "default": 0.0,
    },
    "gemini": {
        "gemini-2.0-flash-001": 0.0,
        "default": 0.0,
    },
    "github_models": {
        "gpt-4o-mini": 0.00015,
        "gpt-4o": 0.0025,
        "default": 0.00015,
    },
    "cerebras": {
        "llama-3.3-70b": 0.0,
        "default": 0.0,
    },
    "mistral": {
        "mistral-large-latest": 0.002,
        "mistral-small-latest": 0.001,
        "default": 0.001,
    },
    "ollama": {
        "llama3": 0.0,
        "default": 0.0,
    },
}


@dataclass
class CostRecord:
    provider_id: str
    model: str
    task_type: TaskType
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    estimated: bool
    session_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = ""


@dataclass
class CostSummary:
    provider_id: str
    model: str
    total_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float


@dataclass
class BudgetConfig:
    name: str
    max_cost_usd: float
    period: str = "monthly"
    provider_id: Optional[str] = None
    max_tokens: Optional[int] = None
    enabled: bool = True


@dataclass
class BudgetAlert:
    budget_name: str
    provider_id: Optional[str]
    current_cost: float
    max_cost: float
    current_tokens: Optional[int]
    max_tokens: Optional[int]
    period: str


class CostTracker:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()
        self._budgets: List[BudgetConfig] = []
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cost_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                model TEXT NOT NULL,
                task_type TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                estimated INTEGER NOT NULL DEFAULT 0,
                session_id TEXT,
                error TEXT,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cost_provider
                ON cost_records (provider_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_cost_timestamp
                ON cost_records (timestamp);
            CREATE TABLE IF NOT EXISTS budgets (
                name TEXT PRIMARY KEY,
                max_cost_usd REAL NOT NULL,
                period TEXT NOT NULL DEFAULT 'monthly',
                provider_id TEXT,
                max_tokens INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1
            );
        """)
        self._load_budgets()

    def _load_budgets(self) -> None:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT name, max_cost_usd, period, provider_id, max_tokens, enabled FROM budgets"
        )
        self._budgets = []
        for row in cursor:
            self._budgets.append(BudgetConfig(
                name=row["name"],
                max_cost_usd=row["max_cost_usd"],
                period=row["period"],
                provider_id=row["provider_id"],
                max_tokens=row["max_tokens"],
                enabled=bool(row["enabled"]),
            ))

    def get_model_price(self, provider_id: str, model: str) -> float:
        provider_pricing = MODEL_PRICING.get(provider_id, {})
        return provider_pricing.get(model, provider_pricing.get("default", 0.0))

    def estimate_cost(self, provider_id: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        price_per_1k = self.get_model_price(provider_id, model)
        return (prompt_tokens + completion_tokens) / 1000.0 * price_per_1k

    def record_cost(
        self,
        provider_id: str,
        model: str,
        task_type: TaskType,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: Optional[str] = None,
        error: Optional[str] = None,
        estimated: bool = True,
    ) -> CostRecord:
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = self.estimate_cost(provider_id, model, prompt_tokens, completion_tokens)
        ts = datetime.now(timezone.utc).isoformat()
        record = CostRecord(
            provider_id=provider_id,
            model=model,
            task_type=task_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            estimated=estimated,
            session_id=session_id,
            error=error,
            timestamp=ts,
        )
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO cost_records "
                "(provider_id, model, task_type, prompt_tokens, completion_tokens, "
                "total_tokens, cost_usd, estimated, session_id, error, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (provider_id, model, task_type.value, prompt_tokens, completion_tokens,
                 total_tokens, cost_usd, int(estimated), session_id, error, ts),
            )
            conn.commit()
        except Exception as e:
            logger.warning("Failed to persist cost record: %s", e)
        logger.debug(
            "Cost recorded: %s/%s %s tokens=%d cost=$%.6f",
            provider_id, model, task_type.value, total_tokens, cost_usd,
        )
        return record

    def get_cost_summary(
        self,
        provider_id: Optional[str] = None,
        since: Optional[str] = None,
    ) -> List[CostSummary]:
        conn = self._get_conn()
        conditions = []
        params: list = []
        if provider_id:
            conditions.append("provider_id = ?")
            params.append(provider_id)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        where = " AND ".join(conditions) if conditions else "1"
        # WHERE fragments are fixed literals assembled above; every value remains bound.
        cursor = conn.execute(
            f"SELECT provider_id, model, "  # nosec B608
            "COUNT(*) as total_calls, "
            "SUM(prompt_tokens) as total_prompt, "
            "SUM(completion_tokens) as total_completion, "
            "SUM(total_tokens) as total_tokens, "
            "SUM(cost_usd) as total_cost "
            f"FROM cost_records WHERE {where} "
            "GROUP BY provider_id, model "
            "ORDER BY total_cost DESC",
            params,
        )
        result = []
        for row in cursor:
            result.append(CostSummary(
                provider_id=row["provider_id"],
                model=row["model"],
                total_calls=row["total_calls"],
                total_prompt_tokens=row["total_prompt"],
                total_completion_tokens=row["total_completion"],
                total_tokens=row["total_tokens"],
                total_cost_usd=round(row["total_cost"], 6),
            ))
        return result

    def get_total_cost(self, provider_id: Optional[str] = None, since: Optional[str] = None) -> float:
        summaries = self.get_cost_summary(provider_id=provider_id, since=since)
        return round(sum(s.total_cost_usd for s in summaries), 6)

    def get_total_tokens(self, provider_id: Optional[str] = None, since: Optional[str] = None) -> int:
        summaries = self.get_cost_summary(provider_id=provider_id, since=since)
        return sum(s.total_tokens for s in summaries)

    def set_budget(self, config: BudgetConfig) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO budgets (name, max_cost_usd, period, provider_id, max_tokens, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (config.name, config.max_cost_usd, config.period,
             config.provider_id, config.max_tokens, int(config.enabled)),
        )
        conn.commit()
        self._load_budgets()

    def delete_budget(self, name: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM budgets WHERE name = ?", (name,))
        conn.commit()
        self._load_budgets()

    def get_budgets(self) -> List[BudgetConfig]:
        return list(self._budgets)

    def check_budgets(self) -> List[BudgetAlert]:
        alerts: List[BudgetAlert] = []
        now = datetime.now(timezone.utc)
        for budget in self._budgets:
            if not budget.enabled:
                continue
            since = self._period_start(now, budget.period)
            current_cost = self.get_total_cost(provider_id=budget.provider_id, since=since)
            current_tokens: Optional[int] = None
            if budget.max_tokens is not None:
                current_tokens = self.get_total_tokens(provider_id=budget.provider_id, since=since)
            if current_cost >= budget.max_cost_usd or (
                budget.max_tokens is not None and current_tokens is not None
                and current_tokens >= budget.max_tokens
            ):
                alerts.append(BudgetAlert(
                    budget_name=budget.name,
                    provider_id=budget.provider_id,
                    current_cost=current_cost,
                    max_cost=budget.max_cost_usd,
                    current_tokens=current_tokens,
                    max_tokens=budget.max_tokens,
                    period=budget.period,
                ))
        return alerts

    @staticmethod
    def _period_start(dt: datetime, period: str) -> str:
        if period == "daily":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == "weekly":
            monday = dt - timedelta(days=dt.weekday())
            return monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == "yearly":
            return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        else:
            return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
