# Changelog

## v1.0.0 (2026-07-22)

First public release.

### Core Architecture
- Pipeline Obligatorio — 7-step execution pipeline (Identity → Intent → Decision → Policy → Gateway → Execution → Quality → Audit)
- Quality Gate — Automatic secrets detection and redaction on AI outputs
- YAML Policies with Hot Reload — Security policies as code, hot-reloaded without restart
- Skill Engine & Planner — Composable skill execution with automatic planning
- Deep Context Engine — Rich context building for AI interactions
- Simulation Engine — Dry-run execution with metadata extraction
- Agent Registry — Multi-agent orchestration with specialized AI personas
- Model Router — Provider fallback chaining (Ollama → OpenAI → Anthropic)

### Security & Hardening
- Windows ACL Hardening — DACL-based file permission enforcement
- Circuit Breakers — Automatic failure isolation for tools and models
- Rate Limiter — Sliding window rate limiting per actor+path
- Vault — Encrypted secrets storage with audit trail
- Emergency Stop — Immediate halt for all execution
- Granular Permissions — Auto/Confirm/Manual levels + custom rules
- Offline Queue — Queued execution during disconnection with auto-sync
- Security Headers — CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- Input Validation — Request size limits, Content-Length validation
- Pentest Gate — Release-blocking adversarial security verification suite

### Fleet & Remote
- Device Registry — Automatic device registration on startup with metadata
- Pairing System — Token-based device pairing with QR code support
- Remote Proxy — HTTP proxy server with TLS support for cross-device access
- Configuration Sync — Push/pull configuration and device data between peers
- Sync Activity Log — Persistent history of sync operations

### Plugins
- Manifest-based extensibility with hook system
- Plugin Templates — minimal, with_code, data_collector, system_monitor, security_scanner
- Marketplace — Remote registry browsing and URL-based installation
- Permission Declaration — Plugins declare required permissions in manifest
- Integrity Verification — SHA-256 checksum verification on plugin exports

### Triggers & Automation
- Schedule Triggers — Cron-based periodic execution
- Event Triggers — System metric thresholds (CPU, memory, disk)
- Webhook Triggers — HTTP endpoint listeners
- Trigger History — Execution logging with status tracking

### Observability & Monitoring
- System Monitor — Real-time CPU, memory, disk, network, process, GPU metrics
- Observability Service — Execution traces with latency tracking
- Cost Tracker — Per-model cost tracking with budget alerts
- Performance Alerts — Anomaly detection on execution latency
- Alert Manager — Multi-source alert aggregation with acknowledgment

### Knowledge & Memory
- Knowledge Base — Document storage with semantic search
- File Pipeline — Document ingestion (PDF, DOCX, images) with text extraction
- Episodic Memory — Session-based interaction memory
- Learned Preferences — User preference learning from feedback
- Profile System — User profiles with themes, presets, and history

### Admin & Diagnostics
- Admin UI — Configuration CRUD, backup/restore, log viewer, health diagnostics
- Error Recovery Panel — Circuit breaker status, offline queue management, health checks
- In-App Help — Topic-based documentation browser with search and categories
- Proactive Suggestions — Passive system monitoring with dismissable recommendations

### UI & UX
- Dashboard with real-time metrics and AI analysis
- Chat interface with multi-agent support
- Execute tab with permission-aware execution
- Console with command history and quick actions
- Fleet management with device registry and sync controls
- Plugin manager with marketplace and detail views
- Permissions and Policies management with visual editors
- Triggers, Vault, Knowledge Base, Reports, Memory, Alerts
- Admin panel with diagnostics, config, backup, log viewer
- Help tab with categorized documentation
- Proactive tab with system suggestions and trends
- Onboarding Wizard — 6-step guided first-run experience with tab navigation
- Connection Status — Real-time sidecar health with retry button
- Error Recovery — Exponential backoff retry, friendly error messages, offline banner
- Welcome Card — Quick-start actions on Dashboard for new users

### CI/CD & Release (Fase 10 — Distribution & Supply Chain)
- 4 CI/CD Workflows — ci, release, publish-general, security-adversarial
- Dependabot — Automated dependency updates for pip, npm, cargo, GitHub Actions
- SBOM Generation — CycloneDX for npm, Python, Rust dependencies
- SLSA Attestations — Build provenance attestations
- Signed Releases — Authenticode + updater signatures with verification
- Release Contract Tests — 9 gates validating version consistency, signing, packaging
- Release Metadata — SHA256SUMS, release-manifest.json, smoke tests
- Windows MSI installer via Tauri with updater (server + public key)
- Two-job release pipeline: unprivileged build → privileged signing
- All CI actions and tools pinned by immutable version
- Legacy Python installer (`sidecar/installer.py`) deprecated
- Release metadata falls back to `sentinel/sentinel` (no historical AIVO refs)
- Conservative mode (`SENTINEL_CONSERVATIVE_MODE=1`) blocks write/executor tools

### Quality & Stability (Fase 8 — Runtime)
- Executor and filesystem services offload blocking I/O to threads
- Semaphore (max 5) caps concurrent subprocesses
- 23 budget assertions in benchmarks (context_with_proc at 12000ms)
- Monotonic clocks for all duration measurements
- Monotonic timestamps in SQLite schema

### Product Coherence (Fase 9 — UX & Trust)
- Settings stripped of stubs (System/About tabs, unused sidebar)
- Cost display in Workbench message meta
- API Key dialog converted to shared Modal component
- Onboarding + SimulationConfirmDialog accessibility (Escape, focus, role)
- usePolling hook fixed with recursive setTimeout + AbortController
- API module reorganized to `src/api/`

### E2E & Pentest (Fase 11)
- 3 real-binary E2E suites: install→configure→execute→restart→persist→uninstall
- Schema migration N-1→N and failed update recovery tests
- Uninstall residue verification (DB, config, temp cleanup)
- 40 adversarial security tests covering IPC, vault, path traversal, Fleet, audit
- PathGuardian traversal detection
- Vault encryption/decryption and tamper detection

### Observability & Monitoring
- ObservabilityService with execution tracing, latency percentiles, error categories
- PipelineMetricsService with component durations, tool usage, throughput, bottlenecks
- CostTracker with per-provider/model pricing, budgets, alerts
- Circuit breakers per provider with OPEN/CLOSED/HALF_OPEN states
- Health endpoints: /admin/health, /observability/*, /error-recovery/health-check
- Performance alerts with anomaly detection

### Migration from v0.x
- `/api/*` endpoints are deprecated (respond with `Deprecation` header)
- Use `/v1/execute` instead
- JSON files migrated to SQLite automatically
