# FASE 8 — Security Hardening: Complete Analysis

> **Status:** Pre-implementation analysis (zero code changes yet)
> **Based on:** Full codebase audit (87 Python files, 26 test files, 574 tests)
> **Current maturity:** Security 3/10

---

## Table of Contents

1. [Request Path Tracing](#1-request-path-tracing)
2. [Current Security Boundary Map](#2-current-security-boundary-map)
3. [AIVO_TESTING Impact Analysis](#3-aivotesting-impact-analysis)
4. [Target Architecture Design](#4-target-architecture-design)
5. [Incremental Implementation Plan](#5-incremental-implementation-plan)
6. [Test Strategy](#6-test-strategy)
7. [Risk Register for Changes](#7-risk-register-for-changes)

---

## 1. Request Path Tracing

### 1.1 Full Request Flow Diagram

```
                         ┌──────────────────────┐
                         │     HTTP CLIENT        │
                         │  (Tauri / Browser /    │
                         │   curl / test client)  │
                         └──────────┬───────────┘
                                    │ HTTP request
                                    ▼
                    ┌───────────────────────────────┐
                    │        FastAPI Middleware       │
                    │  ┌─────────────────────────┐   │
                    │  │ CORS (configured)         │   │
                    │  └─────────────────────────┘   │
                    │  ┌─────────────────────────┐   │
                    │  │ Rate Limit (main.py:69)   │   │
                    │  │  ❌ Bypass if AIVO_TESTING│   │
                    │  └─────────────────────────┘   │
                    │  ┌─────────────────────────┐   │
                    │  │ ? AUTH MIDDLEWARE         │   │
                    │  │  ❌ DOES NOT EXIST        │   │
                    │  └─────────────────────────┘   │
                    └──────────────┬────────────────┘
                                   │ route match
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ROUTE HANDLER                                   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ sentinel_bridge.py:                                              │  │
│  │                                                                  │  │
│  │  POST /process          → _require_admin? → ❌ NO CHECK         │  │
│  │  GET  /capabilities     → _require_admin? → ❌ NO CHECK         │  │
│  │  GET  /goals            → _require_admin? → ❌ NO CHECK         │  │
│  │  GET  /goals/matches    → _require_admin? → ❌ NO CHECK         │  │
│  │  GET  /last-execution   → _require_admin? → ❌ NO CHECK         │  │
│  │  POST /goals            → _require_admin() → ✅ YES (but ❌      │  │
│  │  DELETE /goals/{id}     → _require_admin() → ✅ YES   bypass)  │  │
│  │  PATCH /goals/{id}      → _require_admin() → ✅ YES             │  │
│  │  GET  /goals/audit      → _require_admin() → ✅ YES             │  │
│  │                                                                  │  │
│  │  _require_admin():                                               │  │
│  │    if AIVO_TESTING: return  ← ❌ BYPASS                          │  │
│  │    if level != "admin": raise PermissionError                    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ executor.py:                                                     │  │
│  │  POST /command  → _auth() → ToolGateway.execute("executor.command")│
│  │  POST /launch   → _auth() → ToolGateway.execute("executor.launch")│
│  │  POST /kill/{pid} → _auth() → ToolGateway.execute("executor.kill")│
│  │                                                                  │  │
│  │  _auth(): reads x-user-id, x-client-id from headers              │  │
│  │  ⚠️ These are OPTIONAL headers — no validation                   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ filesystem.py:                                                   │  │
│  │  POST /read    → _auth() → ToolGateway.execute("filesystem.read") │  │
│  │  POST /write   → _auth() → ToolGateway.execute("filesystem.write")│  │
│  │  GET  /list    → _auth() → ToolGateway.execute("filesystem.list") │  │
│  │  GET  /search  → _auth() → ToolGateway.execute("filesystem.search")│
│  │                                                                  │  │
│  │  Same _auth() pattern: optional headers, no validation           │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ Other endpoints (NO auth at all):                                │  │
│  │  GET /api/permissions/status                                     │  │
│  │  POST /api/permissions/level                                     │  │
│  │  POST /api/permissions/emergency/{action}                        │  │
│  │  POST /api/permissions/confirm                                   │  │
│  │  POST /api/permissions/blocklist                                 │  │
│  │  GET /api/audit/log                                              │  │
│  │  DELETE /api/audit/log                                           │  │
│  │  GET /api/proactive/suggestions                                  │  │
│  │  POST /api/proactive/suggestions/{id}/execute                    │  │
│  │  GET /api/ai/config                                              │  │
│  │  POST /api/ai/config                                             │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    TOOL GATEWAY (sentinel/core/tool_gateway.py)        │
│                                                                       │
│  1. Lookup tool by ID                                                 │
│  2. Enrich context (system info)                                      │
│  3. Policy evaluation (if policy engine + required_permissions)       │
│     ┌──────────────────────────────────────────────────────────────┐  │
│     │ POLICY ENGINE (sentinel/core/policy_engine.py)                │  │
│     │                                                               │  │
│     │  PermissionLevelPolicy (security_policies.py):                │  │
│     │    - "view"   → dangerous=DENY, read=ALLOW, write=DENY       │  │
│     │    - "confirm"→ dangerous=REQUIRE_CONFIRM, read=ALLOW         │  │
│     │    - "auto"   → dangerous=REQUIRE_CONFIRM, read=ALLOW         │  │
│     │    - "admin"  → ALLOW everything                              │  │
│     │                                                               │  │
│     │  EmergencyStopPolicy:                                         │  │
│     │    - If EMERGENCY_STOP[0] == True → DENY all                  │  │
│     └──────────────────────────────────────────────────────────────┘  │
│  4. Tool execution                                                    │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    TOOL EXECUTOR                                       │
│                                                                       │
│  executor_command_tool.py:                                            │
│    → ExecutorService.execute()                                        │
│      → validate_command()     ← ⚠️ Partial validation                 │
│      → classify_command()                                             │
│      → check_permission()     ← ⚠️ Duplicate permission check         │
│      → _exec_safe()           ← ⚠️ Still runs cmd.exe /c {raw}       │
│                                                                       │
│  filesystem_read_tool.py:                                             │
│    → FilesystemService.read_file()                                    │
│      → PathGuardian.validate_read()  ← ✅ Good path validation        │
│                                                                       │
│  filesystem_write_tool.py:                                            │
│    → FilesystemService.write_file()                                   │
│      → PathGuardian.validate_write() ← ✅ Good path validation        │
└──────────────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    OS / FILESYSTEM                                     │
│                                                                       │
│  subprocess.Popen(["cmd.exe", "/c", command])  ← ⚠️ Raw command       │
│  open(path, "r")                                 ← ⚠️ If path bypassed │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Auth Decision Points — Complete Matrix

| Endpoint | Method | Auth Check | Auth Type | Can Bypass? | Risk |
|----------|--------|:----------:|:---------:|:-----------:|:----:|
| `/api/sentinel/process` | POST | ❌ **None** | — | Direct HTTP | **CRITICAL** |
| `/api/sentinel/capabilities` | GET | ❌ **None** | — | Direct HTTP | **CRITICAL** |
| `/api/sentinel/goals` | GET | ❌ **None** | — | Direct HTTP | **CRITICAL** |
| `/api/sentinel/goals/matches` | GET | ❌ **None** | — | Direct HTTP | **CRITICAL** |
| `/api/sentinel/last-execution` | GET | ❌ **None** | — | Direct HTTP | **CRITICAL** |
| `/api/sentinel/goals` | POST | `_require_admin` | Permission level | AIVO_TESTING | High |
| `/api/sentinel/goals/{id}` | DELETE | `_require_admin` | Permission level | AIVO_TESTING | High |
| `/api/sentinel/goals/{id}` | PATCH | `_require_admin` | Permission level | AIVO_TESTING | High |
| `/api/sentinel/goals/audit` | GET | `_require_admin` | Permission level | AIVO_TESTING | High |
| `/api/executor/command` | POST | Gateway policy | Permission level | Level change | High |
| `/api/executor/launch` | POST | Gateway policy | Permission level | Level change | High |
| `/api/executor/kill/{pid}` | POST | Gateway policy | Permission level | Level change | High |
| `/api/fs/read` | POST | Gateway policy | Permission level | Level change | Med |
| `/api/fs/write` | POST | Gateway policy | Permission level | Level change | High |
| `/api/fs/list` | GET | Gateway policy | Permission level | Level change | Med |
| `/api/fs/search` | GET | Gateway policy | Permission level | Level change | Med |
| `/api/permissions/status` | GET | ❌ **None** | — | Direct HTTP | Medium |
| `/api/permissions/level` | POST | ❌ **None** | — | Direct HTTP | **CRITICAL** |
| `/api/permissions/emergency/{action}` | POST | ❌ **None** | — | Direct HTTP | High |
| `/api/permissions/confirm` | POST | ❌ **None** | — | Direct HTTP | High |
| `/api/permissions/blocklist` | POST | ❌ **None** | — | Direct HTTP | High |
| `/api/audit/log` | GET | ❌ **None** | — | Direct HTTP | Low |
| `/api/audit/log` | DELETE | ❌ **None** | — | Direct HTTP | Low |
| `/api/proactive/suggestions` | GET | ❌ **None** | — | Direct HTTP | Low |
| `/api/proactive/suggestions/{id}/execute` | POST | Gateway policy | Permission level | Level change | High |
| `/api/ai/config` | GET | ❌ **None** | — | Direct HTTP | Medium |
| `/api/ai/config` | POST | ❌ **None** | — | Direct HTTP | Medium |

### 1.3 Data Flow — Executor Command (Critical Path)

```
User sends: {"command": "powershell -Command Get-ChildItem C:\\"}
                │
                ▼
executor.py:POST /command
    req = CommandRequest(command=..., timeout=30, confirmed=False, action_id="")
                │
                ▼
    _auth(request) → AuthContext(user_id="local", client_id="127.0.0.1", session_id="")
                │
                ▼
    ToolGateway.execute("executor.command", params, {auth})
                │
                ├── PolicyEngine.evaluate() → PermissionLevelPolicy
                │   └── If level="admin" → ALLOW
                │
                ▼
    ExecutorCommandTool.execute(params, context)
                │
                ├── PathGuardian.validate_write() ← Only for file ops
                │
                ▼
    ExecutorService.execute(command, timeout, confirmed, action_id)
                │
                ├── validate_command(command)
                │   ├── Empty check
                │   ├── Length check (8192 max)
                │   ├── Metachar detection
                │   └── Destructive pattern check
                │
                ├── classify_command(command) → "safe" | "unknown" | destructive
                │
                ├── check_permission("execute", command)
                │   └── Duplicate of gateway policy check
                │
                ├── _exec_safe(command)
                │   ├── shlex.split(cmd) → try to parse
                │   ├── if first_token in ALLOWED_SAFE_CMDS → cmd.exe /c cmd
                │   ├── if args[0] is file → run directly
                │   └── else → cmd.exe /c cmd  ← ⚠️ DEFAULT FALLBACK
                │
                ▼
    subprocess.Popen(["cmd.exe", "/c", command])
                │
                ▼
            OS EXECUTES THE COMMAND
```

**Key observation:** The `_exec_safe` method at `executor_service.py:142-151` has a fallthrough that passes the raw command to `cmd.exe /c`. The `ALLOWED_SAFE_CMDS` check only affects *how* it runs, not *if* it runs.

---

## 2. Current Security Boundary Map

### 2.1 Trust Boundaries

```
┌──────────────────────────────────────────────────────────────────┐
│  UNTRUSTED (Network/Remote)                                       │
│                                                                   │
│  Any process on localhost:8765 can send requests                  │
│  (Tauri WebView, browser dev tools, curl, malware)                │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP (no encryption, localhost only)
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  SEMI-TRUSTED (FastAPI Process)                                   │
│                                                                   │
│  Authentication:    ❌ None                                       │
│  Authorization:     ⚠️ Per-endpoint opt-in                       │
│  Input validation:  ⚠️ Partial (executor has basic checks)        │
│  Rate limiting:     ⚠️ Has AIVO_TESTING bypass                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ Python function calls
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  POLICY ENFORCEMENT (ToolGateway + PolicyEngine)                   │
│                                                                   │
│  Only applies to tool executions (executor, filesystem, system)   │
│  Does NOT protect:                                                 │
│    - sentinel_bridge endpoints (process, capabilities, etc.)      │
│    - permissions endpoint (level change!)                          │
│    - ai_config endpoint                                            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  PRIVILEGED (Service Layer)                                       │
│                                                                   │
│  Can execute commands, read/write files, access OS APIs           │
│  ExecutorService:  ⚠️ Partial validation, fallthrough to cmd.exe │
│  FilesystemService: ✅ PathGuardian protects                      │
└──────────────────────────┬───────────────────────────────────────┘
                           │ OS syscalls
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  SYSTEM (Operating System)                                        │
│                                                                   │
│  Full access to Windows API, file system, registry, network       │
│  Runs as current user (no sandboxing)                             │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 AIVO_TESTING Bypass Map

```
AIVO_TESTING=1 is set in:
  ✅ conftest.py (line 9)
  ✅ All 26 test files (line ~5 in each)
  ✅ GitHub CI (ci.yml line 51)

AIVO_TESTING is checked in:
  ❌ sentinel_bridge.py:20  → _require_admin() returns immediately
  ❌ main.py:71             → rate_limit_middleware skips check
  ❌ proactive.py:24        → start_engine() skips startup

Bypass effect:
  - sentinel_bridge: ANY permission level can create/delete/patch goals
  - main.py: Rate limiting disabled entirely
  - proactive.py: Engine not started during tests

39 total occurrences in codebase (including report).
```

---

## 3. AIVO_TESTING Impact Analysis

### 3.1 Why AIVO_TESTING Exists

The `AIVO_TESTING` variable was introduced to allow tests to:
1. Call endpoints without permission level restrictions
2. Start the FastAPI app without the proactive engine background thread
3. Avoid rate limiting during test runs

**The fundamental problem:** `AIVO_TESTING` was added as a shortcut instead of designing proper test isolation mechanisms.

### 3.2 How to Replace It

| Current behavior | Replacement strategy |
|-----------------|---------------------|
| `_require_admin()` returns early | Mock `_require_admin` or use test auth token |
| Rate limiting disabled | Test client doesn't trigger rate limits (single-thread, sequential) |
| Proactive engine not started | Already controlled by `start_engine()` event — keep check but rename to `_SKIP_BACKGROUND_TASKS` or make injectable |

### 3.3 Places That Need Changes

**Production code (4 files):**

| File | Line | Current | Replacement |
|------|------|---------|-------------|
| `sentinel_bridge.py` | 20-21 | `if AIVO_TESTING: return` | Remove bypass entirely; tests will provide auth |
| `main.py` | 71 | `if AIVO_TESTING: return await call_next(request)` | Remove; rate limiting is harmless in tests |
| `proactive.py` | 24 | `if not AIVO_TESTING: _svc.start()` | Change to `if os.environ.get("AIVO_SKIP_BACKGROUND", "") != "1":` |
| `test_goal_management.py` | 378,388,397 | `mock env AIVO_TESTING=""` | Remove mocks; use auth token instead |

**Test files (26 files):**
- Remove `os.environ["AIVO_TESTING"] = "1"` from all test files
- Replace with auth token/token mechanism
- The `conftest.py` should set the test token globally

**CI config (1 file):**
- Remove `AIVO_TESTING: "1"` from `ci.yml`
- If needed, replace with `AIVO_SKIP_BACKGROUND: "1"` for proactive engine

### 3.4 Test Impact Summary

```
Files to modify: 31 (4 production + 26 test + 1 CI)
Files to add: 1 (test auth middleware or fixture)
Lines to change: ~35 (each test file has 1 line + conftest + 4 production)
Impact on test count: 0 (tests continue to pass)
```

---

## 4. Target Architecture Design

### 4.1 Target Request Flow

```
                         ┌──────────────────────┐
                         │     HTTP CLIENT        │
                         └──────────┬───────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────────────────────┐
                    │           FASTAPI MIDDLEWARE LAYER             │
                    │                                               │
                    │  ┌───────────────────────────────────────┐    │
                    │  │ 1. AUTH MIDDLEWARE (NEW)              │    │
                    │  │    - Extracts token from header       │    │
                    │  │    - Validates token                  │    │
                    │  │    - Sets request.state.identity      │    │
                    │  │    - Rejects if no valid token        │    │
                    │  │                                       │    │
                    │  │    Token types:                       │    │
                    │  │      • "local" → default for desktop  │    │
                    │  │      • "admin" → admin-level access   │    │
                    │  │      • test tokens → for pytest only  │    │
                    │  └───────────────────────────────────────┘    │
                    │                                               │
                    │  ┌───────────────────────────────────────┐    │
                    │  │ 2. RATE LIMIT MIDDLEWARE (HARDENED)   │    │
                    │  │    - No AIVO_TESTING bypass           │    │
                    │  │    - Configurable limits              │    │
                    │  │    - Per-identity tracking (not IP)   │    │
                    │  └───────────────────────────────────────┘    │
                    └──────────────────┬────────────────────────────┘
                                       │ identity in request.state
                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  IDENTITY CONTEXT (created by auth middleware)                       │
│                                                                     │
│  @dataclass                                                          │
│  class Identity:                                                     │
│      token_type: str       # "local" | "admin" | "test" | "bearer"  │
│      token_value: str      # actual token string                     │
│      level: str            # "admin" | "confirm" | "auto" | "view"  │
│      source: str           # "header" | "default" | "test"          │
│                                                                     │
│  Default for local-only: Identity("local", "local", "admin", "default")│
└──────────────────────────┬──────────────────────────────────────────┘
                           │ passed to route handlers via request.state
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ROUTE HANDLERS                                                      │
│                                                                     │
│  sentinel_bridge.py:                                                │
│    POST /process  → Identity with level >= "confirm" required      │
│    GET /capabilities → Identity with level >= "view" required      │
│    POST /goals    → Identity with level == "admin" required        │
│    ...                                                              │
│                                                                     │
│  executor.py:                                                       │
│    POST /command  → Identity with level >= "confirm" required      │
│    ...         → ToolGateway.execute() also checks permissions     │
│                                                                     │
│  permissions.py:                                                    │
│    POST /level   → Identity with level == "admin" required         │
│    POST /emergency → Identity with level == "admin" required       │
│    GET /status   → Identity with level >= "view" required          │
│    ...                                                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
                    ┌─────────────────────────────────────────────┐
                    │  AUTHORIZATION LAYER (new helper)           │
                    │                                             │
                    │  def require_level(identity: Identity,       │
                    │                minimum: str):                │
                    │      if level_rank(identity.level) <         │
                    │         level_rank(minimum):                 │
                    │          raise HTTPException(403)            │
                    │                                             │
                    │  Usage:                                     │
                    │    require_level(identity, "admin")          │
                    └─────────────────────────────────────────────┘
                           │
                           ▼
                    ┌─────────────────────────────────────────────┐
                    │  ToolGateway + PolicyEngine (unchanged)     │
                    │                                             │
                    │  Gateway receives auth in context            │
                    │  PolicyEngine evaluates permissions          │
                    └─────────────────────────────────────────────┘
                           │
                           ▼
                    ┌─────────────────────────────────────────────┐
                    │  Tool Execution (with reinforced validation) │
                    │                                             │
                    │  executor_tool: validate + sanitize command  │
                    │  filesystem_tool: validate paths             │
                    └─────────────────────────────────────────────┘
```

### 4.2 Level Hierarchy

```
RANK  LEVEL         ACCESS
────  ────────────  ─────────────────────────────────────
4     admin         Full access to everything
3     confirm       Execute actions (dangerous needs confirmation)
2     auto          Auto-execute safe actions
1     view          Read-only access
0     (none)        No access (default deny)
```

### 4.3 Token Types

| Token Type | Source | Default Level | Purpose |
|-----------|--------|:------------:|---------|
| `local` | Default (no header) | `admin` | Desktop app → full local access |
| `admin` | `Authorization: Bearer <admin-token>` | `admin` | Remote admin access |
| `user` | `Authorization: Bearer <user-token>` | `confirm` | Regular user access |
| `test` | `X-Test-Token: valid-test-token` | `admin` | Test framework only |

### 4.4 Architecture Decisions

**Decision 1: Middleware over per-route decorator**
- ✅ All requests authenticated at entry point
- ✅ No risk of forgetting auth on new endpoints
- ❌ Requires middleware to be first (before route handler)
- *Why:* A single missing `@require_auth` on a new endpoint is a security hole. Middleware eliminates that class of bug.

**Decision 2: Identity in request.state, not global**
- ✅ Thread-safe (no global mutable state)
- ✅ Compatible with async FastAPI
- ✅ Tests can set request.state directly
- *Why:* Global auth state would break async and require cleanup. `request.state` is the FastAPI-idiomatic approach.

**Decision 3: Default "local" identity with admin level**
- ✅ No config needed for desktop-only usage
- ✅ Backward compatible (current behavior preserved)
- ✅ Remote/network access requires explicit token
- *Why:* The primary use case is local desktop app. We don't want to break that flow. But network access must be explicitly secured.

**Decision 4: Remove AIVO_TESTING entirely, replace with test token**
- ✅ Tests authenticate explicitly (no magic bypass)
- ✅ Test token is validated by the same middleware
- ✅ No env var can disable security
- *Why:* The env var bypass pattern is the root cause of several risk items. Eliminating it fixes all env-var-based bypasses.

**Decision 5: Executor command sanitization — layer at service level**
- ✅ Multiple layers of defense (gateway policy + service validation + OS safety)
- ✅ Command allowlist with fallback to `cmd.exe /c` (⚠️ risky) — improve by requiring explicit allow
- *Why:* The `ALLOWED_SAFE_CMDS` approach is correct but the fallthrough to `cmd.exe /c` must be hardened.

---

## 5. Incremental Implementation Plan

### Phase 8.1 — Auth Middleware + Identity (Foundation)

**Goal:** Create the authentication middleware and identity system. All endpoints get a minimum `view` level requirement by default.

| Step | File | Change | Risk | Tests Needed |
|:----:|------|--------|:----:|:------------:|
| 8.1.1 | NEW: `sidecar/modules/auth.py` | Create `AuthMiddleware`, `Identity` dataclass, `require_level()` helper | Low | Unit test middleware, identity parsing |
| 8.1.2 | `sidecar/main.py` | Add `AuthMiddleware` to app (before routes, after CORS) | Medium | All existing tests still pass |
| 8.1.3 | `sidecar/modules/security/interfaces.py` | Move `AuthContext` → new `Identity` pattern; keep backward compat | Low | Existing auth context tests pass |
| 8.1.4 | All route files | Remove any inline `_auth()` functions; use `request.state.identity` | Medium | Per-endpoint behavior unchanged |

**Acceptance:**
- All endpoints return 403 if accessed without valid identity
- "local" default identity has admin-level access (backward compat)
- All 574 tests pass with auth token fixture

### Phase 8.2 — Remove AIVO_TESTING Bypass

**Goal:** Eliminate all AIVO_TESTING checks from production code.

| Step | File | Change | Risk | Tests Needed |
|:----:|------|--------|:----:|:------------:|
| 8.2.1 | `sidecar/modules/sentinel_bridge.py:20-21` | Remove `if AIVO_TESTING: return` from `_require_admin()` | High | Test admin endpoints with auth token |
| 8.2.2 | `sidecar/main.py:71` | Remove `if AIVO_TESTING` from rate limit middleware | Low | Rate limit tests |
| 8.2.3 | `sidecar/modules/proactive.py:24` | Change to `AIVO_SKIP_BACKGROUND` env var | Low | Proactive engine tests |
| 8.2.4 | `sidecar/tests/conftest.py:9` | Remove `os.environ["AIVO_TESTING"] = "1"` | High | All tests use auth token |
| 8.2.5 | All 26 test files | Remove `os.environ["AIVO_TESTING"] = "1"` from each | Medium | Batch edit, verify each |
| 8.2.6 | `.github/workflows/ci.yml:51` | Remove `AIVO_TESTING: "1"` from CI | Low | CI passes |
| 8.2.7 | `test_goal_management.py:378,388,397` | Remove mock of AIVO_TESTING env var | Medium | Those 3 tests pass |

**Critical dependency:** Phase 8.1 must be complete first — tests need the auth token fixture to authenticate without AIVO_TESTING.

**Acceptance:**
- No `AIVO_TESTING` references remain in production code
- No env var can disable security checks
- All tests authenticate via test token
- CI validates without `AIVO_TESTING`

### Phase 8.3 — Executor Command Hardening

**Goal:** Prevent arbitrary command execution. Commands must pass allowlist or explicit approval.

| Step | File | Change | Risk | Tests Needed |
|:----:|------|--------|:----:|:------------:|
| 8.3.1 | `sentinel/adapters/executor_tool.py` | Add command whitelist check before execution | High | Test blocked commands, allowed commands |
| 8.3.2 | `sidecar/services/executor_service.py:142-151` | Fix `_exec_safe` fallthrough — don't default to `cmd.exe /c` for unlisted commands | Critical | Test every command path |
| 8.3.3 | `sidecar/services/executor_service.py` | Add strict arg validation (no shell metacharacters without explicit allow) | Medium | Test metachar handling |
| 8.3.4 | `sidecar/services/executor_service.py` | Expand `ALLOWED_SAFE_CMDS` or make configurable | Low | Update tests |
| 8.3.5 | `sentinel/adapters/executor_tool.py` | Remove `PathGuardian` call from executor (filesystem tools handle paths) | Low | Path-based command tests |

**Design:**
```
Command → Allowlist Check
  ├── In ALLOWED_SAFE_CMDS → Execute (cached, fast path)
  ├── In user-configured allowlist → Execute
  ├── Requires confirmation → PendingActions + return needs_confirm
  └── Blocked → Return error
```

**Acceptance:**
- Commands not in allowlist cannot execute without confirmation
- `_exec_safe` does not fall through to raw `cmd.exe /c`
- Shell metacharacters require explicit allow
- All existing executor tests pass

### Phase 8.4 — Filesystem Path Hardening

**Goal:** Ensure filesystem operations validate paths before execution.

| Step | File | Change | Risk | Tests Needed |
|:----:|------|--------|:----:|:------------:|
| 8.4.1 | `sidecar/modules/filesystem.py` | Verify all endpoints use gateway (already do) | Low | Code review |
| 8.4.2 | `sidecar/services/filesystem_service.py` | Add path canonicalization check (beyond PathGuardian) | Medium | Traversal edge cases |
| 8.4.3 | `sentinel/adapters/filesystem_tool.py` | Add context injection (identity) into file operations | Low | Identity propagation |
| 8.4.4 | `sidecar/modules/security/path_policy.py` | Review and expand `BLOCKED_PATHS`, `SENSITIVE_PATTERNS` | Low | New blocked paths tested |

**Acceptance:**
- All filesystem endpoints validated by PathGuardian
- Path traversal attempts rejected
- Sensitive system paths blocked
- All path tests pass

### Phase 8.5 — Secure Unauthenticated Endpoints

**Goal:** Every endpoint requires minimum `view` level (already covered by middleware in 8.1 — this is the audit pass).

| Step | File | Change | Risk | Tests Needed |
|:----:|------|--------|:----:|:------------:|
| 8.5.1 | `sidecar/modules/sentinel_bridge.py` | Verify all 10 endpoints pass identity | Low | Integration test per endpoint |
| 8.5.2 | `sidecar/modules/permissions.py` | Add `require_level(identity, "admin")` to POST /level, POST /emergency | Medium | Permission level tests |
| 8.5.3 | `sidecar/services/ai_service.py` | Add `require_level(identity, "admin")` to config endpoints | Medium | Config endpoint tests |
| 8.5.4 | Audit pass: review every route handler | Ensure no endpoint lacks auth | Low | Full endpoint scan |

**Acceptance:**
- 100% of endpoints require minimum `view` level
- Admin-only endpoints (level change, emergency, goal management) require `admin`
- Integration test verifies each endpoint's required level

### Phase 8.6 — Rate Limiting Hardening

**Goal:** Rate limiting cannot be bypassed by env var.

| Step | File | Change | Risk | Tests Needed |
|:----:|------|--------|:----:|:------------:|
| 8.6.1 | `sidecar/main.py:69-82` | Remove `AIVO_TESTING` bypass from rate limit middleware | Low | Rate limit tests |
| 8.6.2 | `sidecar/main.py` | Make rate limit configurable via app config | Low | Config override test |

**Acceptance:**
- Rate limiting always active
- Configurable through proper config, not env var

### Phase 8.7 — Security Integration Tests

**Goal:** Verify all security hardening through automated tests.

| Step | File | Change | Risk | Tests Needed |
|:----:|------|--------|:----:|:------------:|
| 8.7.1 | `sidecar/tests/test_auth_integration.py` (NEW) | Create comprehensive auth tests | Medium | All auth scenarios |
| 8.7.2 | `sidecar/tests/test_security_verification.py` | Update with new auth patterns | Medium | Security assertions |
| 8.7.3 | Full test run | Verify 574+ tests pass | Low | CI green |

**Acceptance:**
- Auth integration tests cover: valid token, invalid token, expired token, missing token, level enforcement
- All existing security tests pass with new auth

---

## 6. Test Strategy

### 6.1 Auth Fixture (replaces AIVO_TESTING)

```python
# In conftest.py, replace AIVO_TESTING with:

@pytest.fixture(autouse=True)
def auth_headers():
    """Provide a valid test token for all test requests."""
    return {"Authorization": "Bearer test-admin-token"}

@pytest.fixture
def admin_client(client, auth_headers):
    """Test client with admin auth headers."""
    from fastapi.testclient import TestClient
    # Bind headers to the test client
    client.headers.update(auth_headers)
    yield client
```

### 6.2 Test Categories

| Category | Tests | Coverage |
|----------|:-----:|:--------:|
| Auth middleware unit | 10+ | Token parsing, validation, expiry, missing |
| Level enforcement | 15+ | Each endpoint with different levels |
| Executor command validation | 20+ | Allowlist, metachar, destructive patterns |
| Filesystem path protection | 15+ | Traversal, blocked paths, symlinks |
| Rate limiting | 5+ | Limit enforcement, reset |
| Security regression | 267 | Existing test_security_verification.py |

### 6.3 What Won't Change

- Tests that don't touch auth (goal scoring, intent engine, memory) will still pass
- Test count will increase (new auth tests)
- Existing test assertions remain valid

---

## 7. Risk Register for Changes

| ID | Risk | Phase | Mitigation | Rollback |
|:--:|------|:-----:|:-----------|:--------:|
| C01 | Auth middleware blocks legitimate requests | 8.1 | Default "local" identity with admin level preserves current behavior | Remove middleware line from main.py |
| C02 | Test token leaks to production | 8.2 | Test token only valid when `_test_mode` flag set; never in production | N/A (design prevents) |
| C03 | Executor command allowlist breaks existing functionality | 8.3 | Allow all currently-allowed commands; only block unlisted + destructive | Revert allowlist check |
| C04 | Filesystem path change breaks user workflows | 8.4 | PathGuardian already exists; changes are additive | Revert specific path rule |
| C05 | Test count drops below 574 | 8.2 | Run full suite after each change; add compensating tests | Fix failing tests before merge |

---

## Summary: Implementation Order

```
Phase 8.1: Auth Middleware + Identity
  └── Enables →
Phase 8.2: Remove AIVO_TESTING
  └── Enables →
Phase 8.3: Executor Command Hardening
Phase 8.4: Filesystem Path Hardening
Phase 8.5: Secure All Endpoints (audit pass)
Phase 8.6: Rate Limiting Hardening
Phase 8.7: Security Integration Tests
```

**Each phase is independently testable and revertible.**
**No phase breaks backward compatibility.**
**Total estimated effort: ~12 days.**

---

*End of FASE 8 Security Hardening Analysis*
