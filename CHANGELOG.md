# Changelog

## v1.0.0 (2026-07-15)

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

### CI/CD & Release
- 4 CI/CD Workflows — ci, release, publish-general, security-adversarial
- Dependabot — Automated dependency updates for pip, npm, cargo, GitHub Actions
- SBOM Generation — CycloneDX for npm, Python, Rust dependencies
- SLSA Attestations — Build provenance attestations
- Signed Releases — Authenticode + updater signatures with verification
- Release Contract Tests — 9 gates validating version consistency, signing, packaging
- Release Metadata — SHA256SUMS, release-manifest.json, smoke tests
- Windows MSI installer via Tauri with updater (server + public key)
- 800+ tests across frontend (27 files) and backend (50+ files)

### Migration from v0.x
- `/api/*` endpoints are deprecated (respond with `Deprecation` header)
- Use `/v1/execute` instead
- JSON files migrated to SQLite automatically
