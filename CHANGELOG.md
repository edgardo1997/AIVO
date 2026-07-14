# Changelog

## v1.0.0 (2026-07-10)

First public release.

### Features
- Pipeline Obligatorio: all execution goes through 7-step pipeline
- Quality Gate: automatic secrets detection and redaction
- YAML Policies: all policies configurable without code changes
- Hot Reload: edit policies without restarting
- SQLite Unification: single database for all data
- API v1: professional REST API with OpenAPI spec
- UI v2: 3 screens — Execute (with pipeline viz), Policies (with YAML editor), Audit (with timeline)
- Docker image with multi-stage build (~50MB)
- Windows MSI installer via Tauri
- 616 passing tests

### Migration from v0.x
- `/api/*` endpoints are deprecated (respond with `Deprecation` header)
- Use `/v1/execute` instead
- JSON files migrated to SQLite automatically
