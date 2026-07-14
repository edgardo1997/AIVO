# Sentinel Constitution

## Identity

Sentinel is a **Trust Layer** — a security layer between AI agents and the operating system.  
It is NOT a chatbot, dashboard, IDE, agent, or model provider.

## Principles

1. **No bypass**: Every tool execution MUST go through the full pipeline:
   Identity → Intent → Decision → Policy → Gateway → Execution → Quality → Audit
2. **Policies as Code**: All security policies MUST be YAML files, never hardcoded in Python
3. **Least Privilege**: Default effect is DENY; access must be explicitly granted
4. **Audit Everything**: Every execution produces one complete audit record
5. **Local-First**: All data stays on the user's machine — no telemetry, no cloud dependency
6. **Sensitive Data Protection**: Quality Gate MUST scan all outputs for secrets before returning to the caller

## Project Structure

```
sentinel/          # Core Trust Layer (framework-agnostic)
  core/            # Pipeline: orchestrator, gateway, policies, quality gate
  policies/        # Policy definitions + YAML loader
  tools/           # First-party tool implementations
sidecar/           # FastAPI server + module wrappers
  modules/         # Route handlers, services
  routers/         # API v1 routers
  services/        # Business logic services
  repositories/    # SQLite data access
  tests/           # Test suite (600+ tests)
docs/              # Documentation
src/               # React frontend (3 screens: Execute, Policies, Audit)
```

## Release Policy

- v1.0.0: First public release
- v1.x: Backward-compatible additions
- v2.0: May break backward compatibility
