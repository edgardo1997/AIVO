# AIVO — Full Codebase Audit

> **Date:** 2026-07-17  
> **Scope:** All source, config, infra, and documentation files

---

## 1. Project Overview

AIVO is a multi-agent AI framework with three vertically integrated subsystems:

| Subsystem | Role |
|-----------|------|
| **Sentinel** | Python orchestrator — planning, execution, quality gating, agent lifecycle |
| **Sidecar** | Python bridge — CLI host, executor daemon, Python sandbox |
| **Frontend** | TypeScript/React UI — chat interface, execution viewer, settings |

The project **builds and deploys as a single Electron app** on Windows (x64). It uses **pnpm** as the frontend package manager and **Poetry** for Python.

**Build output:** `aivo-app/dist/AIVO Setup <version>.exe` (NSIS installer).

---

## 2. Technology Stack

### 2.1 Frontend (Electron + React)
- **Node:** ^18.18.2 (pinned in `package.json`)
- **pnpm:** 9.4.0 (via `packageManager` field)
- **Electron:** ^33.1.0
- **react:** ^18.3.1
- **Vite:** ^6.0.0 (with `electron-vite` for main/preload/renderer builds)
- **TypeScript:** ^5.6.2
- **Styling:** Tailwind CSS ^3.4.6 — no component library (raw JSX + Tailwind utility classes)
- **State management:** Zustand ^4.5.2 — one store per concern (chat, settings, etc.)
- **Testing:** Vitest ^2.0.5 (configuration present, no tests in `src/`)
- **Linting:** eslint ^9.0.0 + `eslint-plugin-react-hooks` + TypeScript-ESLint

### 2.2 Python Subsystems (Sentinel & Sidecar)
- **Python:** ^3.12 (pinned in `pyproject.toml`)
- **Package manager:** Poetry (lock files: `sentinel/poetry.lock`, `sidecar/poetry.lock`)
- **Framework:** FastAPI (sidecar serves an HTTP API); Sentinel uses no web framework
- **AI/ML:** Instructor (structured output from LLMs), LiteLLM (multi-provider LLM client)
- **Code execution:** Docker SDK for Python (sandboxed execution)
- **Parsing:** tree-sitter (Python grammar) for code understanding in Sentinel
- **Linting:** ruff (config present in both Python subprojects)

### 2.3 Infrastructure / DevOps
- **CI:** GitHub Actions (`.github/workflows/electron-build.yml` — Windows build only)
- **Code signing:** Azure Key Vault + Azure Trusted Signing (certificates stored in Key Vault)
- **Build system:** `electron-vite` + `electron-builder` (NSIS installer)
- **Docker:** Docker Compose available for sidecar services (e.g., sandbox-container)

---

## 3. Frontend Architecture

### 3.1 Vite/Electron Entry Points (`src/`)

```
src/
├── main/          # Electron main process
│   └── index.ts   # BrowserWindow creation, IPC handlers, app lifecycle
├── preload/       # Preload script (contextBridge)
│   └── index.ts   # Exposes safe API to renderer
└── renderer/      # React app
    └── src/
        ├── App.tsx
        ├── components/     # UI components (Chat, Execute, Session, Settings)
        ├── hooks/          # Custom hooks (useChat, useAivoSettings)
        ├── lib/            # Utilities, API calls
        ├── providers/
        └── stores/         # Zustand stores (chat, session, settings)
```

**Key observations:**

- **`Chat.tsx`** — Main chat UI with message list, input, streaming indicator, thought bubbles. Uses `useChat` hook.
- **`Execute.tsx`** — Execution panel with diff view, file tree selector, audit trail, execution status.
- **`Session.tsx`** — Session management: create, switch, rename, delete sessions.
- **`Settings.tsx`** — Settings modal covering LLM provider keys, sidebar toggle, theme, agent mode, pipeline, etc.
- **`SplashScreen.tsx`** — Startup loading screen shown before app is ready.
- **`App.tsx`** — Root layout with sidebar, main content area (split into Chat + Execute), session bar.
- **`useAivoSettings`** — Generic hook using `localStorage` for per-setting persistence.
- **`useChat`** — Manages messages array, streaming state, connection status.
- **Chat store** (`zustand`) — Handles messages, streaming, context variables; generates IDs with `crypto.randomUUID()`.
- **Session store** (`zustand`) — Handles session CRUD, current session selection, active tools tracking.
- **Settings store** (`zustand`) — Handles settings modal open/close, theme toggle.

### 3.2 Component Map

| Component | File | Purpose |
|-----------|------|---------|
| MessageList | Chat.tsx | Renders chat bubbles, thought bubbles, streaming indicators |
| ChatInput | Chat.tsx | Text input with send button, keyboard shortcut handling |
| Execute | Execute.tsx | Execution panel with diff view and file tree |
| Session | Session.tsx | Session management panel |
| Settings | Settings.tsx | Settings modal |
| SplashScreen | SplashScreen.tsx | Loading screen |
| App | App.tsx | Root layout |

### 3.3 Styling
- Tailwind CSS utility classes throughout
- `globals.css` for custom scrollbar, fonts (Geist), and base resets
- Smooth scrolling, thought bubble anims via Tailwind `animate-*` classes
- `Settings.tsx` uses a generated `tailwindColors` object from `resolveConfig(tailwindConfig)`

---

## 4. Sidecar Architecture (Python Bridge)

**Location:** `sidecar/`

### 4.1 Core Services

| Service | File | Purpose |
|---------|------|---------|
| CLI Host | `services/cli_host.py` | Hosts `SidecarCli` — main entry point the frontend calls |
| Executor Service | `services/executor_service.py` | Manages workback log, execution state, async exec |
| Python Sandbox | `services/python_sandbox.py` | Docker-based sandbox for safely running Python code |
| LLM Service | `services/llm_service.py` | Unified chat completions endpoint via LiteLLM |
| Provider Service | `services/provider_service.py` | Provider registry, API key management, model listing |
| Sandbox Manager | `services/sandbox_manager.py` | Docker container lifecycle (create, start, stop, destroy) |
| Token Tracker | `core/token_tracker.py` | Per-request token usage tracking |
| Sandbox Interface | `core/sandbox_interface.py` | Abstract base for sandbox implementations |
| Session Manager | `core/session_manager.py` | Session CRUD, persistence, workback log |
| Error Handler | `core/error_handler.py` | Structured error responses for the API |
| Router | `api/router.py` | FastAPI router with all REST endpoints |

### 4.2 API Endpoints (FastAPI)

| Method | Path | Handler |
|--------|------|---------|
| POST | `/chat/completions` | `llm_service.chat_completions` — unified LLM call |
| POST | `/execute` | `executor_service.execute_code` — run code in sandbox |
| GET | `/execute/status` | `executor_service.get_execution_status` — polling endpoint |
| GET | `/sessions` | `session_manager.list_sessions` |
| POST | `/sessions` | `session_manager.create_session` |
| GET | `/sessions/{id}` | `session_manager.get_session` |
| DELETE | `/sessions/{id}` | `session_manager.delete_session` |
| POST | `/sessions/select` | `session_manager.select_session` |
| POST | `/sessions/switch` | `session_manager.switch_session` |
| POST | `/execute/log-entry` | `executor_service.append_log_entry` — add workback entry |
| GET | `/execute/log` | `executor_service.get_log` — retrieve workback log |
| PATCH | `/execute/log/{index}` | `executor_service.update_log_entry` |
| GET | `/providers` | `provider_service.list_providers` |
| POST | `/providers/validate` | `provider_service.validate_api_key` |

### 4.3 Startup / CLI
- **`main.py`** — CLI entry point with Typer for `sidecar serve`, `sidecar sandbox`, `sidecar execute`
- **`api/server.py`** — FastAPI app factory with CORS, lifespan (start/stop sandbox), router mounting
- **`api/dependencies.py`** — FastAPI dependency injection for session scope

### 4.4 Key Design Decisions
- **Lifespan-based sandbox management** — Docker container created on startup, torn down on shutdown
- **`workback_log`** — Per-session list of workback entries (task descriptions, statuses) managed via REST
- **Token tracking** — Accumulated per-request in `TokenTracker`; reset on new session
- **Async execution** — `executor_service` uses `asyncio` for non-blocking code execution
- **Error handler middleware** — Catches unhandled exceptions, returns structured `{"error": ..., "detail": ...}`

---

## 5. Sentinel Architecture (Orchestrator)

**Location:** `sentinel/`

### 5.1 Core Modules

| Module | Purpose |
|--------|---------|
| `core/agent.py` | Base `Agent` class with provider, model, and tool support |
| `core/planner.py` | `Planner` — creates step-by-step plans from tasks |
| `core/executor.py` | `Executor` — executes planned steps, manages code gen/runtime |
| `core/quality_gate.py` | `QualityGate` — validates plans & results before/after execution |
| `core/tracker.py` | `Tracker` — maintains execution state, context, results |
| `core/pipeline.py` | `Pipeline` — orchestrates Agent → Planner → Executor → QualityGate |
| `core/workback.py` | `Workback` — workback logging, session history |
| `core/hook.py` | `Hook` — events & lifecycle hooks system |
| `core/tool.py` | `Tool` — tool definitions, tool registry |
| `core/types.py` | Type aliases, `SentinelConfig` Pydantic model |
| `core/providers/openai_compatible.py` | Provider implementation for OpenAI-compatible APIs |
| `core/providers/instructor_client.py` | `InstructorClient` — wraps Instructor for structured output |
| `core/providers/anthropic.py` | Anthropic Claude provider |
| `core/providers/google.py` | Google Gemini provider |
| `core/skills/code_generator.py` | `CodeGenerator` — generates Python code from plans |
| `core/skills/code_reader.py` | `CodeReader` — reads & summarizes existing code via tree-sitter |
| `core/skills/file_ops.py` | `FileOps` — file creation, diff generation, snapshot management |
| `core/skills/skill_registry.py` | `SkillRegistry` — registers & retrieves skills |
| `ctl/startup.py` | CLI startup using Typer |
| `ctl/commands/` | CLI subcommands |

### 5.2 Key Design Decisions
- **Plugin-style architecture** — Providers and skills are registered dynamically
- **Instructor for structured output** — All LLM calls go through `InstructorClient` for type-safe, validated responses
- **Layered pipeline** — `Pipeline.x()` wraps Agent → Planner → Executor → QualityGate in one call
- **tree-sitter for code understanding** — `CodeReader` parses ASTs to understand existing code structure
- **Event hooks** — `Hook` system allows subscribing to lifecycle events (pre/post plan, execute, validate)

---

## 6. Cross-Cutting Concerns

### 6.1 Configuration & Environment
- **Frontend:** Environment variables via `.env` files loaded by Vite
- **Python:** Configuration via Pydantic models (`sentinel_config.py`, `sidecar_config.py`, provider configs)
- **API keys:** Expected via environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
- **Paths:** Sidecar and Sentinel look for their configs in `~/.config/aivo/` by default

### 6.2 Testing
- **Frontend:** Vitest configured with jsdom — zero test files in `src/`
- **Sentinel:** Pytest configured — few unit tests exist under `sentinel/tests/`
- **Sidecar:** Pytest configured — no test files found
- **Coverage:** No coverage configuration in any project

### 6.3 Linting & Formatting
- **Frontend:** ESLint with flat config — `eslint.config.mjs` in root
- **Python (both):** ruff configured in `pyproject.toml` — line length 120, I (imports) + E (pycodestyle) + F (pyflakes) rules

### 6.4 Security
- **Secrets:** No `.env` files committed. API keys passed at runtime via env vars.
- **Code execution:** Docker sandbox — untrusted code runs in isolated container
- **No CSP headers** configured in Electron main process
- **`nodeIntegration: false`, `contextIsolation: true`** — standard Electron security

---

## 7. CI/CD Pipeline

**File:** `.github/workflows/electron-build.yml` (Windows-only)

1. Checkout + setup Node ^18 / pnpm
2. Install deps with `pnpm install --frozen-lockfile`
3. Lint with `pnpm lint`
4. Build frontend + electron with `pnpm build`
5. Package installer with electron-builder (NSIS)
6. Sign with Azure Trusted Signing (Key Vault certs)
7. Upload `.exe` as artifact

**Signing secrets injected via GitHub Secrets:**
- `AZURE_KEY_VAULT_URI`
- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`
- `AZURE_CERT_NAME`

---

## 8. Recommendations & Risks

### Critical
1. **Sandbox container hardcoded image** — `python:3.12-slim` is hardcoded; should be configurable and version-pinned by digest
2. **No authentication** on Sidecar API (gRPC or token) — any local process can call endpoints; Electron app should authenticate
3. **Secret scanning** — no pre-commit hooks or CI checks for leaked secrets

### High
4. **Zero frontend test coverage** — `Chat.tsx`, `Execute.tsx`, and all stores have no tests
5. **Sidecar has no tests** — `executor_service.py`, `python_sandbox.py`, `llm_service.py` are untested
6. **No error boundaries in React** — unhandled render errors will crash the app
7. **`any` types** used extensively in stores and components (notably in chat store and file tree)
8. **`eslint-disable` / `@ts-ignore`** comments found in several files suppressing real issues

### Medium
9. **Sentinel tests are minimal** — only a few unit tests exist, no integration tests
10. **No health check endpoint** — frontend cannot detect if Sidecar is alive before making requests
11. **Docker sandbox has no resource limits** (CPU, memory) — risk of fork bombs or OOM
12. **Settings are persisted to `localStorage` only** — no encryption for API keys at rest
13. **No logging framework** — Python modules use `print()` in several places instead of `logging`
14. **NSIS installer only** — no macOS or Linux build targets configured

### Low
15. **`sentinel/` and `sidecar/` have poetry.lock but no `poetry check` in CI** — lock file drift possible
16. **Several `TODO` and `FIXME` comments** scattered across the codebase
17. **CSS uses `@import` in `globals.css`** — consider using `@tailwind base/components/utilities` directives instead
18. **Hardcoded port 8000** for Sidecar API in frontend code

---

## 9. File Inventory (Source Only)

```
aivo-app/
├── .github/workflows/electron-build.yml
├── electron-builder.yml
├── electron.vite.config.ts
├── package.json
├── pnpm-lock.yaml
├── postcss.config.js
├── tailwind.config.ts
├── tsconfig.json / tsconfig.node.json / tsconfig.web.json
├── eslint.config.mjs
├── src/
│   ├── main/index.ts
│   ├── preload/index.ts
│   └── renderer/src/
│       ├── App.tsx
│       ├── components/
│       │   ├── Chat.tsx
│       │   ├── Execute.tsx
│       │   ├── Session.tsx
│       │   ├── Settings.tsx
│       │   └── SplashScreen.tsx
│       ├── hooks/
│       │   ├── useChat.ts
│       │   └── useAivoSettings.ts
│       ├── lib/
│       │   └── utils.ts
│       ├── providers/
│       ├── stores/
│       │   ├── chatStore.ts
│       │   ├── sessionStore.ts
│       │   └── settingsStore.ts
│       └── globals.css

sentinel/
├── pyproject.toml
├── poetry.lock
├── sentinel/
│   ├── __init__.py
│   ├── core/
│   │   ├── agent.py
│   │   ├── planner.py
│   │   ├── executor.py
│   │   ├── quality_gate.py
│   │   ├── tracker.py
│   │   ├── pipeline.py
│   │   ├── workback.py
│   │   ├── hook.py
│   │   ├── tool.py
│   │   ├── types.py
│   │   └── providers/
│   │       ├── openai_compatible.py
│   │       ├── instructor_client.py
│   │       ├── anthropic.py
│   │       └── google.py
│   │   └── skills/
│   │       ├── code_generator.py
│   │       ├── code_reader.py
│   │       ├── file_ops.py
│   │       └── skill_registry.py
│   ├── ctl/
│   │   ├── startup.py
│   │   └── commands/
│   └── tests/

sidecar/
├── pyproject.toml
├── poetry.lock
├── sidecar/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── router.py
│   │   ├── server.py
│   │   └── dependencies.py
│   ├── core/
│   │   ├── token_tracker.py
│   │   ├── sandbox_interface.py
│   │   ├── session_manager.py
│   │   └── error_handler.py
│   └── services/
│       ├── cli_host.py
│       ├── executor_service.py
│       ├── python_sandbox.py
│       ├── llm_service.py
│       ├── provider_service.py
│       └── sandbox_manager.py
```
