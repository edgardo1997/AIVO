-- Initial schema for Persistent Intelligence Storage
-- Applied automatically by StorageEngine._run_inline_migrations()

CREATE TABLE IF NOT EXISTS stored_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    local INTEGER DEFAULT 1,
    capabilities TEXT DEFAULT '[]',
    context_size INTEGER DEFAULT 4096,
    cost REAL DEFAULT 0.0,
    latency_estimate REAL DEFAULT 1.0,
    last_seen TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS feedback_records (
    id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    task_type TEXT DEFAULT '',
    success INTEGER DEFAULT 1,
    quality_score REAL DEFAULT 0.5,
    latency REAL DEFAULT 0.0,
    error TEXT,
    user_id TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_model ON feedback_records(model_id);
CREATE INDEX IF NOT EXISTS idx_feedback_task ON feedback_records(task_type);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_records(created_at);

CREATE TABLE IF NOT EXISTS metric_records (
    id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT DEFAULT '',
    tags TEXT DEFAULT '{}',
    timestamp TEXT
);

CREATE INDEX IF NOT EXISTS idx_metric_component ON metric_records(component);
CREATE INDEX IF NOT EXISTS idx_metric_name ON metric_records(metric_name);
CREATE INDEX IF NOT EXISTS idx_metric_timestamp ON metric_records(timestamp);

CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    role TEXT DEFAULT '',
    content TEXT DEFAULT '',
    context TEXT DEFAULT '{}',
    model_id TEXT DEFAULT '',
    created_at TEXT,
    PRIMARY KEY (session_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_created ON conversations(created_at);

CREATE TABLE IF NOT EXISTS decision_history (
    id TEXT PRIMARY KEY,
    request TEXT,
    intent TEXT DEFAULT '',
    decision TEXT NOT NULL,
    risk_level TEXT DEFAULT '',
    selected_model TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    execution_id TEXT DEFAULT '',
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_decision_model ON decision_history(selected_model);
CREATE INDEX IF NOT EXISTS idx_decision_created ON decision_history(created_at);
CREATE INDEX IF NOT EXISTS idx_decision_decision ON decision_history(decision);

CREATE TABLE IF NOT EXISTS model_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    task_type TEXT DEFAULT '',
    latency REAL DEFAULT 0.0,
    success INTEGER DEFAULT 1,
    quality_score REAL DEFAULT 0.5,
    resource_usage REAL DEFAULT 0.0,
    tokens_used INTEGER DEFAULT 0,
    cost REAL DEFAULT 0.0,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_perf_model ON model_performance(model_name);
CREATE INDEX IF NOT EXISTS idx_perf_task ON model_performance(task_type);
