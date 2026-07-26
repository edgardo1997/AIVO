"""Versioned SQLite schema for aggregate operational telemetry."""

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS telemetry_schema (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS operational_events (
    event_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    issuer_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    health_state TEXT NOT NULL,
    decision_state TEXT NOT NULL,
    integrity_status TEXT NOT NULL,
    record_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timeline_index (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES operational_events(event_id)
        ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS metric_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    decisions INTEGER NOT NULL,
    divergences INTEGER NOT NULL,
    errors INTEGER NOT NULL,
    rollbacks INTEGER NOT NULL,
    health_transitions INTEGER NOT NULL,
    evidence_verified INTEGER NOT NULL,
    evidence_rejected INTEGER NOT NULL,
    canary_observations INTEGER NOT NULL,
    record_hash TEXT NOT NULL
);
"""
