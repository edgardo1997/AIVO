-- FASE 5 — Persistence Intelligence
-- Execution history, model performance index, user preferences

CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    timestamp TEXT,
    user_request TEXT DEFAULT '',
    intent TEXT DEFAULT '',
    task_type TEXT DEFAULT '',
    selected_model TEXT DEFAULT '',
    tools_used TEXT DEFAULT '[]',
    duration REAL DEFAULT 0.0,
    success INTEGER DEFAULT 1,
    failure_reason TEXT,
    risk_level TEXT DEFAULT '',
    cost REAL DEFAULT 0.0,
    confidence_score REAL DEFAULT 0.0,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_executions_timestamp ON executions(timestamp);
CREATE INDEX IF NOT EXISTS idx_executions_model ON executions(selected_model);
CREATE INDEX IF NOT EXISTS idx_executions_task ON executions(task_type);

CREATE TABLE IF NOT EXISTS intelligence_user_preferences (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT DEFAULT 'null',
    source TEXT DEFAULT 'observed',
    evidence_count INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.5,
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_pref_user ON intelligence_user_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_pref_key ON intelligence_user_preferences(key);

CREATE INDEX IF NOT EXISTS idx_perf_model_task ON model_performance(model_name, task_type);
