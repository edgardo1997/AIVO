# Sentinel Product Identity

Sentinel is the product name.

The repository and some legacy runtime identifiers may still use AIVO while the project is migrated. Those names are compatibility anchors, not a second product.

## Canonical naming

- User-facing product name: `Sentinel`
- Backend process/API title: `Sentinel Sidecar`
- Product mission: local trust layer for AI orchestration, policy-gated execution, and audit

## Legacy identifiers kept intentionally

- `com.aivo.desktop` in Tauri config
- `AIVO_TESTING` environment flag
- GitHub updater endpoint containing `AIVO`

These identifiers should not be renamed casually because they can affect installed application identity, test behavior, persistent data, or update delivery.

## Database migration

Sentinel now uses `~/.sentinel/sentinel.db` as the canonical local SQLite database.

On startup, the sidecar copies `~/.aivo.db` to `~/.sentinel/sentinel.db` only when the Sentinel database does not already exist. The legacy database is preserved as a rollback/compatibility source.

Environment variable precedence:

1. `SENTINEL_DB_PATH`
2. `AIVO_DB_PATH` legacy override
3. `~/.sentinel/sentinel.db`

## Required migration before full rename

1. Decide the final Tauri application identifier and updater repository.
2. Provide release notes that explain the local data migration.
3. Remove `AIVO_DB_PATH` only after at least one stable migration release.
4. Only then remove the remaining legacy AIVO compatibility names.
