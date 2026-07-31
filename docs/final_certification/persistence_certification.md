# Persistence Certification

## Data Storage Audit

| Data | Backend | Persists Restart? | Evidence |
|------|---------|-------------------|----------|
| Conversations | SQLite | YES | `sentinel/storage/repositories/conversation_repository.py` |
| Long-term memory | SQLite | YES | `sentinel/storage/repositories/memory_repository.py` |
| Audit logs | SQLite | YES | `sentinel/core/audit_service.py` |
| Performance metrics | **In-memory** | **NO** | `PerformanceIntelligence` stores `List[ExecutionMetrics]` |
| Model rankings | **In-memory** | **NO** | `ModelRanking._scores` is `Dict[str, ModelScore]` |
| User feedback | **In-memory** | **NO** | `FeedbackEngine._history` is `List[UserFeedback]` |
| Model inventory | **In-memory** | **NO** | `ModelRegistry._models` is `Dict[str, ModelMetadata]` |
| API keys | In-memory + DB | PARTIAL | `load_keys_from_db()` / `save_keys_to_db()` |

## Storage Layer Exists But Unused

The `sentinel/storage/` package provides 5 repositories:
- `conversation_repository.py` — WIRED (conversations persist)
- `memory_repository.py` — WIRED (long-term memory persists)
- `metric_repository.py` — **NOT WIRED** (metrics lost on restart)
- `feedback_repository.py` — **NOT WIRED** (feedback lost on restart)
- `ranking_repository.py` — **NOT WIRED** (rankings lost on restart)

## Persistence Test

A simulated restart test would show:
1. START → Create conversation ✅ persists
2. Execute task, record metrics ⚠️ in-memory only
3. Record feedback ⚠️ in-memory only
4. Update ranking ⚠️ in-memory only
5. STOP → START
6. Conversation ✅ recovered
7. Metrics ❌ LOST
8. Feedback ❌ LOST
9. Ranking ❌ LOST

## Verdict: **FAIL** (2/10)

Only conversations, memory, and audit persist. All intelligence data (metrics, ranking, feedback, discovered models) is lost on restart. The storage repositories for metrics, feedback, and ranking exist but are not wired into the runtime.
