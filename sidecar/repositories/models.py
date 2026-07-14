"""SQLAlchemy ORM models matching the existing schema."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Float, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_event_id", "event_id", unique=True, postgresql_where=Column("event_id").is_not(None)),
        Index("idx_audit_entry_hash", "entry_hash", unique=True, postgresql_where=Column("entry_hash").is_not(None)),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="info")
    user: Mapped[str] = mapped_column(String, default="local")
    event_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payload: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    previous_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    entry_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class ExecutionHistory(Base):
    __tablename__ = "execution_history"
    __table_args__ = (Index("idx_exec_timestamp", "timestamp"),)

    execution_id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    utterance: Mapped[str] = mapped_column(String, default="")
    intent: Mapped[str] = mapped_column(String, default="{}")
    plan: Mapped[str] = mapped_column(String, default="{}")
    decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    context_summary: Mapped[str] = mapped_column(String, default="{}")
    step_results: Mapped[str] = mapped_column(String, default="[]")
    tool_result: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)


class PendingAction(Base):
    __tablename__ = "pending_actions"

    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    tool_id: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[str] = mapped_column(String, default="{}")
    reason: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=600)
    confirmed: Mapped[int] = mapped_column(Integer, default=0)


class EmergencyStop(Base):
    __tablename__ = "emergency_stop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    provider: Mapped[str] = mapped_column(String, default="ollama")
    model: Mapped[str] = mapped_column(String, default="")
    capabilities: Mapped[str] = mapped_column(String, default="[]")
    allowed_tools: Mapped[str] = mapped_column(String, default="[]")
    system_prompt: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="idle")
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[str] = mapped_column(String, default="{}")
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class Fleet(Base):
    __tablename__ = "fleet"

    plugin_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[str] = mapped_column(String, default="{}")
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class Trigger(Base):
    __tablename__ = "triggers"
    __table_args__ = (Index("idx_triggers_enabled", "enabled"),)

    trigger_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    conditions: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    action: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    last_fired: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class TriggerHistory(Base):
    __tablename__ = "trigger_history"
    __table_args__ = (
        Index("idx_trigger_history_trigger", "trigger_id"),
        Index("idx_trigger_history_ts", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger_id: Mapped[str] = mapped_column(String, nullable=False)
    condition_met: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timestamp: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class UserPreference(Base):
    __tablename__ = "user_preferences"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, default="local-user")
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="Local User")
    avatar: Mapped[str] = mapped_column(String, default="")
    theme: Mapped[str] = mapped_column(String, default="light")
    timezone: Mapped[str] = mapped_column(String, default="")
    locale: Mapped[str] = mapped_column(String, default="en")
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())


class UserPreferenceV2(Base):
    __tablename__ = "user_preferences_v2"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())
