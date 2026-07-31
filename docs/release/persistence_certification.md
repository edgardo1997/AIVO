# Persistence Certification — Sentinel 1.0 RC

## Data Survival Requirements

| Data | Backend | Persists Restart? | Verified |
|------|---------|-------------------|----------|
| Memory (session history) | `sentinel/core/memory.py` — SQLite via `memory.db` | ✅ Yes | Database persists to disk |
| Conversations | `sentinel/storage/repositories/conversation_repository.py` | ✅ Yes | SQLite migrations v1-v7 |
| Discovered models | `sentinel/core/model_registry.py` | ⚠️ Partial | In-memory only, no DB persistence |
| Metrics | `sentinel/core/performance_intelligence.py` | ❌ **No** | In-memory list, max 10000 cap |
| Ranking | `sentinel/core/model_ranking.py` | ❌ **No** | In-memory Dict[str, ModelScore] |
| Feedback | `sentinel/core/feedback_engine.py` | ❌ **No** | In-memory list, max 10000 cap |
| Audit | `sentinel/core/audit_service.py` | ✅ Yes | SQLite-backed |
| API keys | `ModelRouter._key_map` | ⚠️ Partial | DB load/save via load_keys_from_db/save_keys_to_db |

## Storage Layer (FASE 35)
The `sentinel/storage/` package provides 5 repositories:
- `conversation_repository.py` — conversations
- `memory_repository.py` — long-term memory
- `metric_repository.py` — performance metrics
- `feedback_repository.py` — user feedback
- `ranking_repository.py` — model rankings

Each has SQLite migrations and CRUD operations.

## Gap ⚠️
The in-memory intelligence components (PerformanceIntelligence, ModelRanking, FeedbackEngine) store data in memory but **do not persist to the storage repositories**. On restart:
- Performance metrics are lost
- Model rankings reset
- Feedback history disappears
- Discovered models are lost

## Verdict
**NOT READY** — While persistent storage infrastructure exists (`sentinel/storage/`), the intelligence layer components use in-memory storage and lose all data on restart. The storage repositories are not wired into the runtime.
