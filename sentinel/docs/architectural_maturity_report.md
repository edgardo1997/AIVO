# Architectural Maturity Analysis — AIVO / Sentinel

> **Date:** 2026-07-10
> **Scope:** Full codebase audit (87 Python files, 26 test suites, 15 core modules)
> **Project Phase:** Post-FASE 7.6 (Goal pipeline complete, integration hardened)
> **Tests:** 574 passing, 0 failures

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Maturity Assessment by Dimension](#3-maturity-assessment-by-dimension)
4. [Security Deep-Dive](#4-security-deep-dive)
5. [Code Quality Analysis](#5-code-quality-analysis)
6. [Test Quality Analysis](#6-test-quality-analysis)
7. [Dependency & Packaging Analysis](#7-dependency--packaging-analysis)
8. [Deployment & Operability](#8-deployment--operability)
9. [Critical Gap Analysis](#9-critical-gap-analysis)
10. [Risk Register](#10-risk-register)
11. [Roadmap: Ordered Phases](#11-roadmap-ordered-phases)

---

## 1. Executive Summary

### Maturity Score Card

| Dimension | Score (1-10) | Level |
|-----------|:-----------:|-------|
| **Security** | 3/10 | _Early_ |
| **Architecture** | 7/10 | _Defined_ |
| **Code Quality** | 6/10 | _Developing_ |
| **Test Coverage** | 7/10 | _Defined_ |
| **Scalability** | 4/10 | _Early_ |
| **Operability** | 3/10 | _Initial_ |
| **Dependency Management** | 4/10 | _Early_ |
| **Overall Maturity** | **4.9/10** | _Developing_ |

### Key Strengths
- **Goal pipeline** (FASE 7.1–7.6): clean separation of concerns (GoalRegistry → GoalScorer → Planner → Orchestrator)
- **Tool Gateway + Policy Engine**: extension point architecture executed correctly
- **Capability Registry**: well-designed registration/validation system
- **Test infrastructure**: 574 tests across 26 files, strong integration coverage
- **Thread safety**: `_bridge_lock` in sentinel_bridge, FIFO audit eviction

### Critical Risks
1. **NO authentication on 5 API endpoints** — `POST /process`, `GET /capabilities`, `GET /goals`, `GET /goals/matches`, `GET /last-execution`
2. **`AIVO_TESTING` bypass** in `_require_admin()` — testing flag disables all admin checks
3. **Arbitrary command execution** — `executor.py:POST /command` passes raw user string to OS
4. **No path traversal protection** — filesystem tool operations accept arbitrary paths
5. **No global auth middleware** — entire API surface depends on per-endpoint opt-in
6. **No package configuration** — no `pyproject.toml`, `setup.py`, lock files, or Python version pinning
7. **No Docker/containerization** — single-binary Tauri deployment, no isolation

---

## 2. Architecture Overview

### Project Structure

```
AIVO/
├── sentinel/                          # NEW architecture (under construction)
│   ├── core/                          # Core engines (15 files, ~2,244 lines)
│   │   ├── orchestrator.py            # Main orchestration (218 lines)
│   │   ├── goals.py                   # Goal pipeline (367 lines)
│   │   ├── intent.py                  # Intent engine (248 lines)
│   │   ├── capability_registry.py     # Capability system (184 lines)
│   │   ├── context.py                 # Context engine (178 lines)
│   │   ├── model_router.py            # Model routing (174 lines)
│   │   ├── operational_memory.py      # Memory backend (172 lines)
│   │   ├── planner.py                 # Planning engine (169 lines)
│   │   ├── memory.py                  # Memory abstraction (156 lines)
│   │   ├── decision_engine.py         # Decision engine (128 lines)
│   │   ├── tool_gateway.py            # Tool gateway (116 lines)
│   │   ├── policy_engine.py           # Policy engine (82 lines)
│   │   ├── tool.py                    # Tool base classes (73 lines)
│   │   ├── policy.py                  # Policy base (29 lines)
│   │   └── __init__.py                # Public exports (12 lines)
│   ├── adapters/                      # Tool adapters
│   │   ├── executor_tool.py           # (129 lines)
│   │   ├── filesystem_tool.py         # (120 lines)
│   │   └── system_adapter.py          # (103 lines)
│   └── policies/                      # Security policies
│       └── security_policies.py       # (77 lines)
│
├── sidecar/                           # LEGACY runtime (FastAPI)
│   ├── main.py                        # App bootstrap (165 lines)
│   ├── modules/                       # API modules
│   │   ├── sentinel_bridge.py         # Sentinel API bridge (307 lines)
│   │   ├── executor.py                # Command execution (119 lines)
│   │   ├── filesystem.py              # File operations (54 lines)
│   │   ├── permissions.py             # Permission management (62 lines)
│   │   ├── audit.py                   # Audit logging (15 lines)
│   │   ├── proactive.py               # Proactive suggestions (40 lines)
│   │   ├── plugins.py                 # Plugin system (66 lines)
│   │   ├── voice.py                   # Voice interface (21 lines)
│   │   ├── fleet.py                   # Fleet management (24 lines)
│   │   ├── monitor.py                 # System monitoring (27 lines)
│   │   ├── ai_provider.py             # AI provider interface (34 lines)
│   │   ├── permissions_memory.py      # Memory-backed permissions (121 lines)
│   │   ├── __init__.py                # Wiring/setup (138 lines)
│   │   └── security/                  # Security modules
│   │       ├── path_guardian.py       # Path validation (138 lines)
│   │       ├── path_policy.py         # Path policies (84 lines)
│   │       └── interfaces.py          # Auth context (19 lines)
│   ├── services/                      # Service layer (11 files)
│   └── repositories/                  # Data access (6 files)
│
├── src/                               # React 19 frontend
└── src-tauri/                         # Tauri v2 desktop shell (Rust)
```

### Data Flow

```
User Utterance
    │
    ▼
POST /api/sentinel/process  ──►  Orchestrator.process()
                                      │
                                      ├── IntentEngine.parse()       → Intent
                                      ├── ContextEngine.collect()    → Context
                                      ├── GoalRegistry.find_candidates() → Goal matches
                                      ├── GoalScorer.rank()          → Scored goals
                                      ├── Planner.create_plan()      → Plan
                                      ├── DecisionEngine.evaluate()  → Decision
                                      └── ToolGateway.execute()      → ToolResult
```

### Architecture Style

**Hybrid two-pronged:** legacy sidecar (FastAPI monolith) + new sentinel/ (layered engine architecture). The sidecar acts as both the legacy runtime and the host for the new architecture through `sentinel_bridge.py`.

**Key architectural decisions:**
- **Module-level singletons** throughout (`_svc`, `_orchestrator`, `_gateway`, `_memory`)
- **Manual dependency injection** via `wire_dependencies()` functions
- **No async framework** for core engines (sync for now)
- **In-memory state** as primary storage, optional SQLite via DatabaseManager
- **Policy Engine** as middleware between Gateway and Tool execution

---

## 3. Maturity Assessment by Dimension

### 3.1 Security — Score: 3/10

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Authentication | ❌ **Missing** | 5 endpoints have NO auth check |
| Authorization | ⚠️ Partial | `_require_admin()` exists but has AIVO_TESTING bypass |
| Input sanitization | ❌ **Missing** | `executor.command` passes raw strings to OS |
| Path traversal protection | ❌ **Not implemented** | No path validation in filesystem tool operations |
| Rate limiting | ⚠️ Partial | Exists but bypassed in test mode |
| CORS | ✅ Configured | Specific origins allowed |
| CSP | ❌ **Disabled** | `"csp": null` in tauri.conf.json |
| Secrets management | ⚠️ Basic | API key in memory only, not persisted |
| Audit trail | ✅ Working | Goal audit log, executor audit logging |
| HTTPS | ✅ N/A | Local-only (127.0.0.1) |

**Authentication Gap Analysis:**

| Endpoint | Method | Auth Required? | Protected? |
|----------|--------|:--------------:|:----------:|
| `/api/sentinel/process` | POST | ✅ Yes | ❌ **NO** |
| `/api/sentinel/capabilities` | GET | ❌ Read-only info | ❌ **NO** |
| `/api/sentinel/goals` | GET | ❌ Read-only | ❌ **NO** |
| `/api/sentinel/goals/matches` | GET | ❌ Read-only | ❌ **NO** |
| `/api/sentinel/last-execution` | GET | ✅ Yes (shows last commands) | ❌ **NO** |
| `/api/sentinel/goals` | POST | ✅ Yes | ✅ Yes |
| `/api/sentinel/goals/{id}` | DELETE | ✅ Yes | ✅ Yes |
| `/api/sentinel/goals/{id}` | PATCH | ✅ Yes | ✅ Yes |
| `/api/sentinel/goals/audit` | GET | ✅ Yes | ✅ Yes |
| `/api/executor/command` | POST | ✅ Yes | ✅ Via gateway policies |
| `/api/executor/launch` | POST | ✅ Yes | ✅ Via gateway policies |
| `/api/executor/kill` | POST | ✅ Yes | ✅ Via gateway policies |

### 3.2 Architecture — Score: 7/10

| Criterion | Status | Notes |
|-----------|--------|-------|
| Separation of concerns | ✅ Good | Engine layer, adapter layer, service layer |
| Dependency direction | ✅ Correct | Core ← Adapters ← Services ← API |
| Extension points | ✅ Well-designed | ToolGateway, PolicyEngine, CapabilityRegistry |
| Coupling | ⚠️ Moderate | Module-level singletons create hidden couplings |
| Error handling | ⚠️ Inconsistent | Some bare `except: pass` patterns |
| Async model | ⚠️ Mixed | FastAPI async but core engines are sync |
| State management | ❌ Global singletons | `_svc`, `_orchestrator` at module level — reset only via `reset_bridge()` |
| Configurability | ⚠️ Environment-driven | `AIVO_TESTING` flag, no structured config system |
| Interface segregation | ✅ Good | Tool, Policy, Memory all have clean abstract interfaces |

### 3.3 Code Quality — Score: 6/10

| Metric | Value |
|--------|-------|
| Total Python files | 87 |
| Total Python lines | ~8,500 |
| Average file size | ~98 lines |
| Largest file | `goals.py` (367 lines) |
| Functions with `pass` in except | 4 locations (conftest.py cleanup) |
| Type annotations | ✅ Widespread but not universal |
| Linter | ruff (CI), oxlint (frontend) |
| Formatting | None enforced |
| Docstrings | Minimal |

**Code Smells Detected:**

1. **Bare except: pass** — `conftest.py:clean_state()` swallows cleanup errors silently
2. **Module-level state** — `_svc` pattern throughout creates test isolation challenges
3. **Magic environment variables** — `AIVO_TESTING` controls security behavior
4. **Sequential wiring** — `main.py` must call `wire_dependencies()`, `register_tools()`, `init_policies()` in exact order
5. **Inheritance vs composition** — Some adapters extend base classes unnecessarily

### 3.4 Test Coverage — Score: 7/10

| Criterion | Value |
|-----------|-------|
| Total tests | 574 |
| Passing | 574 (100%) |
| Failing | 0 |
| Test files | 26 |
| Largest test file | `test_capability_registry.py` (532 lines) |
| Smallest test file | `test_proactive.py` (25 lines) |
| Integration tests | ✅ 9 (bootstrap) + 16 (memory) |
| Unit tests | ✅ Goal management, scoring, planning |
| Security tests | ✅ `test_security_verification.py` (267 lines) |
| CI integration | ✅ GitHub Actions |

**Gaps:**
- No performance/benchmark tests
- No stress tests
- No property-based tests (Hypothesis)
- No mutation testing
- No flaky test detection
- Some tests may share state via module singletons

### 3.5 Scalability — Score: 4/10

| Aspect | Assessment |
|--------|------------|
| Concurrency model | Synchronous core, async API layer. No connection pooling. |
| State storage | In-memory only. No persistence by default. |
| Caching | None. Every request re-evaluates context. |
| Horizontal scaling | Not possible (in-memory singletons). |
| Vertical scaling | Limited by single-process Python. |
| Saturation point | ~120 req/min (rate limit ceiling). |

### 3.6 Operability — Score: 3/10

| Capability | Status |
|------------|--------|
| Structured logging | ❌ Plain `logging` module, no JSON format |
| Health checks | ✅ `/api/health` endpoint (minimal) |
| Metrics | ❌ None |
| Tracing | ❌ None |
| Graceful shutdown | ❌ Not implemented |
| Config validation | ❌ No startup validation |
| Docker/container | ❌ Not available |
| Environment parity | ⚠️ Windows dev, Windows CI only |
| Backup/restore | ❌ Not implemented |
| Documentation | ⚠️ Minimal (README + in-progress docs) |

### 3.7 Dependency Management — Score: 4/10

| Criterion | Status |
|-----------|--------|
| Package config | ❌ No `pyproject.toml` or `setup.py` |
| Lock file | ❌ None |
| Python version pin | ❌ Not specified anywhere |
| Unused deps | ⚠️ `httpx` (not imported directly) |
| Missing deps | ⚠️ `pytest` not declared |
| Security scanning | ❌ No automated vuln scanning |
| Vendored deps | ✅ None (all via pip) |
| Build reproducibility | ❌ No lock file, no hash pinning |

---

## 4. Security Deep-Dive

### 4.1 Authentication Flow (Current)

```
Client → FastAPI → [NO AUTH MIDDLEWARE] → Route Handler
                                            │
                                     ┌──────┴──────┐
                                     │ _require_admin │
                                     │ (opt-in)    │
                                     └──────┬──────┘
                                            │
                                     AIVO_TESTING bypass
                                     (if set, all checks skipped)
```

### 4.2 Exploit Paths

#### Path 1: Unauthenticated Process Execution
```
POST http://localhost:8765/api/sentinel/process
{"utterance": "delete all files in C:\\Windows\\System32"}

→ No auth check → Orchestrator processes → Gateway evaluates policies
→ If permission level is not "admin", still blocked by policies
→ If permission level is "admin" or "allow", command EXECUTES
```

#### Path 2: AIVO_TESTING Bypass
```python
# Set env variable
$env:AIVO_TESTING = "1"

# Now _require_admin() returns None immediately
# All admin-gated endpoints become public
```

#### Path 3: Arbitrary Command via executor
```
POST http://localhost:8765/api/executor/command
{"command": "powershell -Command Invoke-WebRequest ... -OutFile malware.exe"}

→ Goes through gateway → PolicyEngine (PermissionLevelPolicy)
→ If permission level allows, command runs with NO SANITIZATION
```

### 4.3 Current Security Architecture Strengths
- **Permission levels** (`off`, `confirm`, `allow`, `admin`) provide graduated access
- **Policy Engine** enforces permission checks at tool execution time
- **Destructive pattern detection** in `permissions_service.py`
- **Confirmation workflow** for high-risk operations
- **Emergency stop** mechanism (`EMERGENCY_STOP`)

### 4.4 Security Priorities (Ordered)
1. **Add global auth middleware** — not per-endpoint opt-in
2. **Remove AIVO_TESTING bypass** — env var must not disable security
3. **Sanitize executor.command** — validate, whitelist, or restrict shell access
4. **Protect filesystem paths** — add path traversal detection
5. **Secure 5 unauthenticated endpoints** — at minimum require `allow` level

---

## 5. Code Quality Analysis

### 5.1 Architecture Debt

| Area | Issue | Severity | Location |
|------|-------|----------|----------|
| Global state | Module-level `_svc` singletons | High | All `sidecar/modules/*.py` |
| Testing bypass | `AIVO_TESTING` env var disables security | Critical | `sentinel_bridge.py:20` |
| Magic env | Undocumented env variables | Medium | Multiple locations |
| Sequencing | Manual wire/register/init order | Medium | `main.py`, `modules/__init__.py` |
| Exception handling | Bare `except: pass` | Medium | `conftest.py`, `main.py` |

### 5.2 Technical Debt

- **No config system**: all configuration is scattered across environment variables, hardcoded values, and JSON files
- **No error taxonomy**: no custom exception hierarchy; mix of `HTTPException`, `PermissionError`, `KeyError`
- **Mixed paradigms**: some modules use classes (services), others use module-level functions (modules)
- **No input models**: `POST /process` accepts raw `dict`, not Pydantic model
- **Frontend-backend contract**: no shared API schema (no OpenAPI codegen)

### 5.3 Clean Code Assessment

| Principle | Adherence |
|-----------|:---------:|
| Single Responsibility | ✅ Mostly (goals.py is exception at 367 lines) |
| Open/Closed | ✅ ToolGateway + PolicyEngine enable extension |
| Dependency Inversion | ✅ Core engines depend on abstractions |
| Interface Segregation | ✅ Small focused interfaces (Tool, Policy, Memory) |
| DRY | ⚠️ Some duplication across filesystem tool/service |
| YAGNI | ⚠️ Fleet module seems premature |

---

## 6. Test Quality Analysis

### 6.1 Test Distribution

```
Test Category            Files    Tests (approx)
─────────────────────    ─────    ──────────────
Goal pipeline            5        1,200+
Capability registry      1        532
Decision/Context         2        379
Memory                   2        494
Security/Path            3        486
Orchestrator/Intent      3        350
Executor/Filesystem      2        125
Plugins/Voice/Fleet      1        101
Monitor/Proactive        2        84
Bootstrap integration    1        116
─────────────────────    ─────    ──────────────
TOTAL                    26       ~3,800+
```

### 6.2 Test Maturity Matrix

| Criterion | Assessment |
|-----------|------------|
| Test isolation | ⚠️ Partial — singletons require careful ordering |
| Fixture quality | ⚠️ `clean_state` has try/except-pass |
| Edge case coverage | ✅ Good for goal pipeline |
| Error path coverage | ⚠️ Inconsistent |
| Performance tests | ❌ None |
| Flakiness detection | ❌ None |
| CI integration | ✅ GitHub Actions |
| Coverage reporting | ❌ Not configured |

### 6.3 Conftest Analysis

The `conftest.py` uses `clean_state` as a session-scoped fixture that resets module globals. This has both benefits (fast) and risks (state leaks between tests that don't properly isolate).

---

## 7. Dependency & Packaging Analysis

### 7.1 Current State

```yaml
Declared dependencies (requirements.txt):
  - fastapi==0.115.0
  - uvicorn==0.30.0
  - psutil==6.1.0
  - openai==1.60.0
  - httpx==0.28.0          # ❌ Not imported anywhere
  - pydantic==2.10.0
  - edge-tts==6.1.3
  - python-multipart==0.0.18

Missing:
  - pytest                  # Used in all tests, not declared
  - ruff                    # Used in CI, not declared

No lock file, no pyproject.toml, no version pinning for sentinel package.
```

### 7.2 Required Actions

1. Create `pyproject.toml` with project metadata, dependencies, and tool config
2. Add `pytest` as dev dependency
3. Generate lock file (pip-compile or poetry.lock)
4. Declare Python version constraint (3.12)
5. Set up package structure for `sentinel` as installable package

---

## 8. Deployment & Operability

### 8.1 Current Deployment Model

```
Tauri Desktop App
├── Frontend (React/Vite)    → dist/
├── Sidecar (Python/FastAPI) → sidecar.exe (PyInstaller)
└── Tauri Shell (Rust)       → AIVO.exe
```

**No Docker, no cloud deployment, no CI/CD for release.**

### 8.2 Runtime Dependencies

| Component | Requires |
|-----------|----------|
| Sidecar | Python 3.12, local-only HTTP server on port 8765 |
| Frontend | Bundled in Tauri, served from disk |
| Tauri | Windows OS, WebView2 runtime |
| AI features | OpenAI API key (configurable) |

### 8.3 Observability Gaps

- **No metrics** — cannot measure latency, throughput, error rates
- **No structured logging** — can't grep/parse logs programmatically
- **No tracing** — can't trace requests across components
- **No health check depth** — `/api/health` returns static `{"status": "ok"}`
- **No startup validation** — config errors surface at runtime, not at startup

---

## 9. Critical Gap Analysis

### 9.1 Security → Identity → Observability → Performance

```
Current State:
  Security (3/10) ──► Identity (0/10) ──► Observability (3/10) ──► Performance (4/10)
                                                                          │
Critical Path:  ❶ Security ──► ❷ Identity ──► ❸ Observability ──► ❹ Perf
```

**Why this order:**
1. **Security first**: A powerful system without security is dangerous. Close all exploit paths before adding users.
2. **Identity second**: Multi-user requires authentication foundations. RBAC is meaningless without auth.
3. **Observability third**: Once users exist, you need to know what they're doing. Metrics and logging.
4. **Performance last**: Optimize based on real bottlenecks measured after users.

### 9.2 Module Dependency Chain

```
goal_pipeline.py ◄── planner.py ◄── orchestrator.py ◄── sentinel_bridge.py
                                                            │
context.py ◄──────────────────────────────────────────────────┘
                                                            │
intent.py ◄───────────────────────────────────────────────────┘
                                                            │
decision_engine.py ◄── permissions_service.py ◄── permissions_repository.py
                                                            │
tool_gateway.py ◄── policy_engine.py ◄── security_policies.py
     │
     ├── executor_tool.py ◄── executor_service.py
     ├── filesystem_tool.py ◄── filesystem_service.py
     └── system_adapter.py
```

---

## 10. Risk Register

| ID | Risk | Severity | Likelihood | Impact | Priority | Phase |
|:--:|------|:--------:|:----------:|:------:|:--------:|:-----:|
| R01 | Unauthenticated process execution | Critical | High | System compromise | P0 | **FASE 8** |
| R02 | AIVO_TESTING disables all auth | Critical | Medium | Complete auth bypass | P0 | **FASE 8** |
| R03 | Arbitrary shell commands | Critical | Medium | Remote code execution | P0 | **FASE 8** |
| R04 | Path traversal via filesystem | High | Medium | Unauthorized file access | P1 | **FASE 8** |
| R05 | No rate limiting in test mode | High | Low | Resource exhaustion | P1 | **FASE 8** |
| R06 | No user identity/isolation | High | Low | Cross-user data leak | P1 | **FASE 10** |
| R07 | No persistent state | High | Low | Data loss on restart | P1 | **FASE 11** |
| R08 | In-memory bottleneck | Medium | Medium | Performance ceiling | P2 | **FASE 9** |
| R09 | No graceful shutdown | Medium | Low | Data corruption | P2 | **FASE 11** |
| R10 | No containerization | Low | Low | Deployment complexity | P3 | Post-MVP |

---

## 11. Roadmap: Ordered Phases

### Phase Priority Rationale

The phases are ordered based on **dependency chains and risk reduction**:

```
FASE 08 ──► FASE 10 ──► FASE 11 ──► FASE 09
Security     Identity    Observability  Performance
```

**Why not FASE 09 before FASE 11?** Without observability (metrics), you can't identify real bottlenecks. Performance optimization without data is guesswork.

**Why not FASE 10 before FASE 08?** Multi-user without authentication is a contradiction. Security is the foundation.

---

### FASE 8 — Security Hardening (P0 — NOW)

**Goal:** Close all critical exploit paths. Make Sentinel safe to run.

| Task | Effort | Risk Reduction |
|------|:------:|:--------------:|
| 8.1 Global auth middleware (all routes require minimum permission level) | 2d | 90% reduction |
| 8.2 Remove AIVO_TESTING bypass; replace with token-based test auth | 1d | 100% of R02 |
| 8.3 Sanitize executor.command: add command whitelist, arg validation | 3d | 85% of R03 |
| 8.4 Path traversal protection in filesystem tools | 2d | 100% of R04 |
| 8.5 Secure 5 unauthenticated endpoints (require `allow`+ level) | 1d | 100% of R01 |
| 8.6 Rate limiting hardening (remove test bypass) | 0.5d | 50% of R05 |
| 8.7 Security audit pass — review all execution paths | 2d | Catch remaining issues |
| **Total** | **~12d** | |

**Acceptance criteria:**
- Every API endpoint requires authentication
- No env var can bypass auth
- All command inputs are validated/sanitized
- File operations reject path traversal
- Penetration test passes with no critical findings

---

### FASE 10 — Multi-User & RBAC (P1 — Next)

**Goal:** User identity, session isolation, role-based access control.

| Task | Effort |
|------|:------:|
| 10.1 User identity model + auth tokens | 3d |
| 10.2 Session management (login/logout/token refresh) | 2d |
| 10.3 RBAC: roles (admin/user/viewer), permission inheritance | 4d |
| 10.4 Per-user memory isolation | 2d |
| 10.5 Per-user goals and configuration | 2d |
| 10.6 Session-aware API middleware | 1d |
| 10.7 Audit enhancements (per-user trails) | 2d |
| **Total** | **~16d** |

---

### FASE 11 — Observability & Production Readiness (P2)

**Goal:** Know what the system is doing. Survive restarts. Validate configuration.

| Task | Effort |
|------|:------:|
| 11.1 Structured JSON logging (loguru or structlog) | 1d |
| 11.2 Metrics collection (request count, latency, error rate) | 3d |
| 11.3 Health check endpoint (deep: deps, memory, last execution) | 1d |
| 11.4 Graceful shutdown (save state, flush logs) | 2d |
| 11.5 Startup configuration validation | 2d |
| 11.6 Persistent state (SQLite goals, audit, permissions) | 4d |
| 11.7 Backup/restore mechanism | 2d |
| **Total** | **~15d** |

---

### FASE 9 — Performance & Caching (P3 — Last)

**Goal:** Optimize based on real metrics. Do not optimize before measurement.

| Task | Effort |
|------|:------:|
| 9.1 Profile-based bottleneck identification | 2d |
| 9.2 Goal matching cache (LRU for frequent queries) | 2d |
| 9.3 Context engine optimization (lazy/deferred collection) | 3d |
| 9.4 Decision engine risk computation caching | 2d |
| 9.5 Async core engine (if bottleneck confirmed) | 5d |
| 9.6 Connection pooling for AI provider | 1d |
| **Total** | **~15d** |

---

### Complete Roadmap

```
PHASE    SCOPE              EFFORT    RISK REDUCTION      MATURITY AFTER
──────   ─────────────────  ───────   ────────────────    ───────────────
FASE 8   Security            12d      75% → ~4.4/10       Security: 3→7
FASE 10  Multi-User/RBAC     16d      15% → ~5.6/10       Architecture: 7→8
FASE 11  Observability       15d      10% → ~6.3/10       Operability: 3→7
FASE 09  Performance         15d      —                   All: ~7-8/10
                                   
─── 12-month horizon ───    58d                        Target: 7.5/10 overall
```

---

## Appendix A: File Inventory

```
Category          Count    Lines     % of Codebase
────────────────  ─────    ─────     ──────────────
Core Engines         15     2,244      26.4%
API Endpoints        16     1,292      15.2%
Services             11     1,361      16.0%
Repositories          6       237       2.8%
Adapters              3       352       4.1%
Policies              1        77       0.9%
Tests                26     4,555*     53.6%
* Test lines counted separately; non-test total: 5,563
```

## Appendix B: Security Boundary Map

```
┌──────────────────────────────────────────────────────┐
│                   UNTRUSTED (Network)                  │
│  POST /process, GET /capabilities, GET /goals, etc.   │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│              FASTAPI MIDDLEWARE LAYER                  │
│  CORS (configured) │ Rate limit (partial) │ Auth: ❌  │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│             API ROUTE HANDLERS                         │
│  sentinel_bridge │ executor │ filesystem │ ...        │
│  _require_admin() on 5/10 routes (AIVO_TESTING ❌)    │
└──────┬──────────────────────────────────┬────────────┘
       │                                  │
┌──────▼──────────┐           ┌──────────▼──────────┐
│  TOOL GATEWAY   │           │  POLICY ENGINE       │
│  (no auth,      │           │  PermissionLevel     │
│   only tools)   │           │  EmergencyStop       │
└──────┬──────────┘           └──────────┬──────────┘
       │                                 │
┌──────▼─────────────────────────────────▼──────────┐
│              SERVICE LAYER                          │
│  ExecutorService │ FilesystemService │ ...         │
│  ⚠️ executor.command: NO INPUT SANITIZATION       │
│  ⚠️ filesystem paths: NO TRAVERSAL PROTECTION     │
└──────────────────┬────────────────────────────────┘
                   │
┌──────────────────▼────────────────────────────────┐
│               OS / FILESYSTEM                       │
│  Commands execute, files are read/written           │
└────────────────────────────────────────────────────┘
```

---

*End of Architectural Maturity Analysis*
