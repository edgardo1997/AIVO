# Sentinel Persistence Inventory

## Stores

| Store | Ruta relativa | Formato | Responsable |
| ----- | ------------- | ------- | ----------- |
| Config | `SENTINEL_DATA_DIR/sentinel.db` | SQLite (aiosqlite) | `StorageEngine` |
| Conversaciones | `sentinel.db` → `conversations` | SQLite | `ConversationRepository` |
| Decisiones | `sentinel.db` → `decisions` | SQLite | `DecisionRepository` |
| Ejecuciones | `sentinel.db` → `executions` | SQLite | `ExecutionRepository` |
| Preferencias | `sentinel.db` → `intelligence_user_preferences` | SQLite | `UserPreferenceRepository` |
| Métricas | `~/.sentinel/metrics.db` | SQLite | `MetricsStore` |
| Feedback | `~/.sentinel/feedback.db` | SQLite | `ModelFeedbackStore` |
| Políticas | `~/.sentinel/policies` | YAML/JSON | `PolicyLoader` |
| Vault | `~/.sentinel/vault` | cifrado + metadatos | `Vault` |
| Logs | `~/.sentinel/logs` | texto / JSONL | `Observability` |

## Variables de entorno

- `SENTINEL_DATA_DIR`: raíz de datos del sidecar.
- `SENTINEL_DATABASE_URL`: override de URL DB.
- `SENTINEL_STORAGE_DATABASE_URL`: override alternativo.

## Aislamiento de pruebas

- `sidecar/tests/conftest.py` sobrescribe `SENTINEL_DATA_DIR` a un directorio temporal.
- No se deben ejecutar pruebas adversariales contra `~/.sentinel` real.

## Recuperación

- `StorageEngine` abre SQLite y ejecuta migraciones.
- SQLite `WAL` puede dejar `-wal` y `-shm`; se manejan por SQLite.
- No existe actualmente un `RecoveryManager` separado.
- Estados terminales deben ser inmutables; validar antes de recovery.
