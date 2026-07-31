"""`sentinel doctor` — CLI diagnostics against the production stack.

Runs the same real checks as the HTTP endpoint `/api/observability/diagnostics`
and prints a human-readable or JSON report. Exit code 0 = all ok, 1 = warnings,
2 = failures.

Usage:
    python -m cli.doctor
    python -m cli.doctor --json
"""

import argparse
import json
import sys
from typing import List, Optional


def _status_symbol(status: str) -> str:
    return {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]"}.get(status, "[?]   ")


def _render_plain(data: dict) -> None:
    print("Sentinel Doctor")
    print("=" * 60)
    summary = data.get("summary", "ok")
    print(f"Summary: {summary.upper()}")
    print("-" * 60)
    for check in data.get("checks", []):
        print(f"  {_status_symbol(check['status'])} {check['name']}: {check['message']}")
        for k, v in check.get("details", {}).items():
            print(f"        {k}: {v}")
    print("=" * 60)


def _exit_code(summary: str) -> int:
    return {"ok": 0, "warn": 1}.get(summary, 2)


def _engine_from_runtime():
    """Resolve the live ObservabilityEngine without a running FastAPI app."""
    try:
        from modules import get_sentinel_orchestrator

        orch = get_sentinel_orchestrator()
        return getattr(orch, "observability", None) or getattr(getattr(orch, "_tool_gateway", None), "_observability", None)
    except Exception:
        return None


def cmd_doctor(args: argparse.Namespace) -> int:
    import contextlib
    import io

    from sentinel.observability.diagnostics import run_diagnostics

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        engine = _engine_from_runtime()
        data = run_diagnostics(engine, include_system=not args.no_system)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        _render_plain(data)
    return _exit_code(data.get("summary", "ok"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentinel doctor", description="Run production diagnostics")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--no-system", action="store_true", help="Skip resource/disk checks")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    return cmd_doctor(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
