"""FASE 6 — Shared metrics registry for the production test report.

Tests record structured results here; `report.py` reads them to generate
`docs/production_test_report.md` at the end of the session.
"""

from threading import Lock
from typing import Any, Dict, List

_lock = Lock()
ALL: Dict[str, List[Dict[str, Any]]] = {}


def record(kind: str, data: Dict[str, Any]) -> None:
    with _lock:
        ALL.setdefault(kind, []).append(dict(data))


def clear() -> None:
    with _lock:
        ALL.clear()


def get(kind: str) -> List[Dict[str, Any]]:
    with _lock:
        return list(ALL.get(kind, []))
