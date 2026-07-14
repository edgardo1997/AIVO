# API Reference

Base URL: `http://127.0.0.1:8765`

## v1 Endpoints

### `POST /v1/execute`

Execute a tool through the full pipeline.

```json
{
  "tool_id": "executor.command",
  "params": { "command": "echo hello", "timeout": 30 },
  "identity": { "user_id": "local", "level": "admin" }
}
```

**Response:**
```json
{
  "success": true,
  "data": { "stdout": "hello\n", "stderr": "", "returncode": 0 },
  "error": null,
  "requires_confirmation": false,
  "duration_ms": 45.2,
  "pipeline": {
    "plan": { "risk_score": 0.5, "steps": [...] },
    "decision": null
  }
}
```

### `GET /v1/policies`

List all loaded policies.

### `POST /v1/policies`

Reload all policies from YAML files.

### `GET /v1/audit`

Query audit log.

| Param  | Type   | Default | Description          |
|--------|--------|---------|----------------------|
| limit  | int    | 100     | Max entries          |
| action | string | —       | Filter by action     |
| since  | string | —       | ISO timestamp filter |

### `DELETE /v1/audit`

Clear all audit entries.

### `GET /v1/agents`

List registered agents.

## Legacy API (Deprecated)

All `/api/*` routes are deprecated since v1.0.0.  
They return the `Deprecation: version="0.1.0"` header and will be removed in v2.0.0.

## OpenAPI Spec

Full spec available at `docs/openapi.yaml` or served at `/docs` when the server is running.
