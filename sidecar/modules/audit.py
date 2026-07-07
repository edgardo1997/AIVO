import json
import logging
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter

log = logging.getLogger("aivo.audit")
router = APIRouter()

AUDIT_FILE = os.path.expanduser("~/.aivo_audit.jsonl")
MAX_ENTRIES = 1000

def log_action(action: str, details: str, status: str = "executed", user: str = "user"):
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "details": details,
        "status": status,
        "user": user,
    }
    try:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        _trim_log()
    except OSError as e:
        log.error("Failed to write audit entry: %s", e)
    except Exception as e:
        log.exception("Unexpected error writing audit log: %s", e)

def _trim_log():
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_ENTRIES:
            with open(AUDIT_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_ENTRIES:])
    except FileNotFoundError:
        pass
    except OSError as e:
        log.debug("Audit trim file error: %s", e)

@router.get("/log")
def get_audit_log(limit: int = 100, action_filter: Optional[str] = None):
    entries = []
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if action_filter and action_filter.lower() not in entry.get("action", "").lower():
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    log.debug("Skipping malformed audit line")
    except FileNotFoundError:
        pass
    except OSError as e:
        log.error("Error reading audit log: %s", e)
    return {"entries": entries[-limit:], "total": len(entries)}

@router.delete("/log")
def clear_audit_log():
    try:
        os.remove(AUDIT_FILE)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.error("Failed to clear audit log: %s", e)
    return {"status": "cleared"}
