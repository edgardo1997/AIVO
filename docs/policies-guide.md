# Policies Guide

Sentinel uses YAML-based policies stored in `~/.sentinel/policies/`.  
No policy is hardcoded in Python — modify the YAML files to change behavior.

## Policy Files

### `security.yaml`

Controls permission levels and tool access.

```yaml
permission_levels:
  view:
    write: deny
    read: allow
    dangerous: deny
  confirm:
    write: allow
    read: allow
    dangerous: require_confirm
  auto:
    write: allow
    read: allow
    dangerous: require_confirm
  admin:
    write: allow
    read: allow
    dangerous: allow

dangerous_tools:
  - "executor.command"
  - "executor.kill"
  - "fs.write"
  - "fs.delete"

tool_permissions:
  executor.command: ["executor.command"]
  filesystem.read: ["filesystem.read"]
  system.info: ["system.read"]
```

### `destructive_patterns.yaml`

Patterns that trigger confirmation prompts. Matched case-insensitively.

```yaml
destructive_patterns:
  - "rm "
  - "del "
  - "format"
  - "shutdown"
  - "reboot"
  - "Remove-Item"
  # ... full list in the file
```

## Hot Reload

Policies are watched for changes. After editing a YAML file:

```bash
curl -X POST http://localhost:8765/v1/policies
```

Or click **Reload from YAML** in the Policies UI tab.

## Permission Levels

| Level   | Read | Write | Dangerous | Use Case          |
|---------|------|-------|-----------|--------------------|
| view    | ✓    | ✗     | ✗         | Read-only access   |
| confirm | ✓    | ✓     | ?         | Default (safe)     |
| auto    | ✓    | ✓     | ?         | Trusted automation |
| admin   | ✓    | ✓     | ✓         | Full access        |

## Adding a Custom Policy

1. Create a Python class extending `Policy` in `sentinel/policies/`
2. Register it in `modules/__init__.py` → `init_policies()`
3. Add its config schema to `sentinel/policies/schema.py`
