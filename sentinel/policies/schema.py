from typing import Any, Dict, List


POLICY_SCHEMA: Dict[str, Any] = {
    "destructive_patterns": {
        "type": "list",
        "items": {"type": "string", "min_length": 1},
        "required": True,
    },
    "dangerous_tools": {
        "type": "list",
        "items": {"type": "string", "min_length": 1},
        "required": True,
    },
    "critical_paths": {
        "type": "list",
        "items": {"type": "string", "min_length": 1},
        "required": False,
    },
    "permission_levels": {
        "type": "dict",
        "keys": {"type": "string", "pattern": r"^(view|confirm|auto|admin)$"},
        "values": {
            "type": "dict",
            "keys": {"type": "string", "pattern": r"^(write|read|dangerous)$"},
            "values": {"type": "string", "pattern": r"^(allow|deny|require_confirm)$"},
        },
        "required": True,
    },
    "emergency_stop": {
        "type": "dict",
        "keys": {"type": "string"},
        "values": {"type": "any"},
        "required": False,
    },
    "tool_permissions": {
        "type": "dict",
        "keys": {"type": "string"},
        "values": {"type": "list", "items": {"type": "string"}},
        "required": False,
    },
}


def validate_policy(data: Dict[str, Any], schema: Dict[str, Any] = None) -> List[str]:
    if schema is None:
        schema = POLICY_SCHEMA
    errors: List[str] = []
    for key, rules in schema.items():
        if rules.get("required") and key not in data:
            errors.append(f"Missing required field: '{key}'")
            continue
        if key not in data:
            continue
        value = data[key]
        expected_type = rules.get("type")
        if expected_type == "list":
            if not isinstance(value, list):
                errors.append(f"'{key}' must be a list, got {type(value).__name__}")
                continue
            item_schema = rules.get("items", {})
            if item_schema:
                for i, item in enumerate(value):
                    if not isinstance(item, str):
                        errors.append(f"'{key}[{i}]' must be a string")
                    elif item_schema.get("min_length") and len(item) < item_schema["min_length"]:
                        errors.append(f"'{key}[{i}]' too short (min {item_schema['min_length']})")
            continue
        if expected_type == "dict":
            if not isinstance(value, dict):
                errors.append(f"'{key}' must be a dict, got {type(value).__name__}")
                continue
            value_schema = rules.get("values", {})
            for k, v in value.items():
                if value_schema.get("type") == "dict" and isinstance(v, dict):
                    nested = validate_policy(v, {"_": value_schema})
                    errors.extend(f"'{key}.{k}.{e.split('.', 1)[1]}' for {e}" for e in nested)
            continue
    return errors
