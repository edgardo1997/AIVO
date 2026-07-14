import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from repositories.database import DatabaseManager
from sentinel.core.agent import AgentSpec, AgentStatus


def _agent_spec_to_db_row(spec: AgentSpec) -> Dict[str, Any]:
    return {
        "agent_id": spec.id,
        "name": spec.name,
        "description": spec.description,
        "provider": spec.provider,
        "model": spec.model,
        "capabilities": json.dumps(spec.capabilities),
        "allowed_tools": json.dumps(spec.allowed_tools),
        "system_prompt": spec.system_prompt,
        "status": spec.status.value if isinstance(spec.status, AgentStatus) else spec.status,
        "max_concurrency": spec.max_concurrency,
        "config": json.dumps(spec.config),
        "created_at": spec.created_at or datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _db_row_to_agent_spec(row: Dict[str, Any]) -> AgentSpec:
    return AgentSpec(
        id=row["agent_id"],
        name=row["name"],
        description=row.get("description", ""),
        provider=row.get("provider", "ollama"),
        model=row.get("model", ""),
        capabilities=json.loads(row.get("capabilities", "[]")),
        allowed_tools=json.loads(row.get("allowed_tools", "[]")),
        system_prompt=row.get("system_prompt", ""),
        status=AgentStatus(row.get("status", "idle")),
        max_concurrency=row.get("max_concurrency", 1),
        config=json.loads(row.get("config", "{}")),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class AgentRepository:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self._db = db or DatabaseManager()

    def list(self) -> List[AgentSpec]:
        rows = self._db.fetchall("SELECT * FROM agents ORDER BY name")
        return [_db_row_to_agent_spec(r) for r in rows]

    def get(self, agent_id: str) -> Optional[AgentSpec]:
        row = self._db.fetchone("SELECT * FROM agents WHERE agent_id = ?", (agent_id,))
        return _db_row_to_agent_spec(row) if row else None

    def create(self, spec: AgentSpec) -> AgentSpec:
        existing = self._db.fetchone("SELECT agent_id FROM agents WHERE agent_id = ?", (spec.id,))
        if existing:
            raise ValueError(f"Agent '{spec.id}' already exists")
        now = datetime.now(timezone.utc).isoformat()
        spec.created_at = spec.created_at or now
        spec.updated_at = now
        row = _agent_spec_to_db_row(spec)
        self._db.execute(
            """INSERT INTO agents (agent_id, name, description, provider, model,
               capabilities, allowed_tools, system_prompt, status,
               max_concurrency, config, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["agent_id"], row["name"], row["description"], row["provider"],
             row["model"], row["capabilities"], row["allowed_tools"],
             row["system_prompt"], row["status"], row["max_concurrency"],
             row["config"], row["created_at"], row["updated_at"]),
        )
        return spec

    def update(self, agent_id: str, updates: Dict[str, Any]) -> Optional[AgentSpec]:
        existing = self._db.fetchone("SELECT * FROM agents WHERE agent_id = ?", (agent_id,))
        if not existing:
            return None
        spec = _db_row_to_agent_spec(existing)
        for key, value in updates.items():
            if key == "status" and isinstance(value, str):
                try:
                    value = AgentStatus(value)
                except ValueError:
                    pass
            setattr(spec, key, value)
        spec.updated_at = datetime.now(timezone.utc).isoformat()
        row = _agent_spec_to_db_row(spec)
        self._db.execute(
            """UPDATE agents SET name=?, description=?, provider=?, model=?,
               capabilities=?, allowed_tools=?, system_prompt=?, status=?,
               max_concurrency=?, config=?, updated_at=?
               WHERE agent_id=?""",
            (row["name"], row["description"], row["provider"], row["model"],
             row["capabilities"], row["allowed_tools"], row["system_prompt"],
             row["status"], row["max_concurrency"], row["config"],
             row["updated_at"], agent_id),
        )
        return spec

    def delete(self, agent_id: str) -> bool:
        cursor = self._db.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
        return cursor.rowcount > 0

    def count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) as cnt FROM agents")
        return row["cnt"] if row else 0

    def upsert(self, spec: AgentSpec) -> AgentSpec:
        existing = self._db.fetchone("SELECT agent_id FROM agents WHERE agent_id = ?", (spec.id,))
        if existing:
            return self.update(spec.id, {
                "name": spec.name, "description": spec.description,
                "provider": spec.provider, "model": spec.model,
                "capabilities": spec.capabilities, "allowed_tools": spec.allowed_tools,
                "system_prompt": spec.system_prompt, "status": spec.status,
                "max_concurrency": spec.max_concurrency, "config": spec.config,
            }) or spec
        return self.create(spec)


SEED_AGENTS: List[AgentSpec] = [
    AgentSpec(
        id="assistant",
        name="General Assistant",
        description="Versatile assistant for everyday tasks: answering questions, research, analysis, and general PC assistance",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash:free",
        capabilities=["general", "research", "analysis"],
        allowed_tools=["ai.chat", "system.info", "filesystem.read"],
        system_prompt="You are a helpful general assistant integrated into Sentinel. Help the user with questions, research, analysis, and everyday PC tasks. Be concise and accurate.",
        status=AgentStatus.ACTIVE,
        max_concurrency=3,
    ),
    AgentSpec(
        id="coder",
        name="Code Assistant",
        description="Specialized in code generation, review, debugging, and software development tasks",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash:free",
        capabilities=["code", "debug", "review"],
        allowed_tools=["filesystem.read", "filesystem.write", "executor.command"],
        system_prompt="You are a code expert integrated into Sentinel. Help with writing, reviewing, debugging, and explaining code. Provide specific, working solutions with clear explanations.",
        status=AgentStatus.ACTIVE,
        max_concurrency=2,
    ),
    AgentSpec(
        id="system-admin",
        name="System Administrator",
        description="System monitoring, diagnostics, optimization, and maintenance tasks",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash:free",
        capabilities=["system", "diagnose", "monitor"],
        allowed_tools=["system.cpu", "system.info", "system.processes", "system.gpu"],
        system_prompt="You are a system administration expert. Help monitor system health, diagnose issues, and optimize performance. Provide actionable recommendations.",
        status=AgentStatus.ACTIVE,
        max_concurrency=1,
    ),
]
