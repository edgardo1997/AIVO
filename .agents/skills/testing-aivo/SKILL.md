---
name: testing-aivo
description: Run and test AIVO locally (Python sidecar + React/Vite frontend). Use when verifying sidecar API behavior, the AI-provider Settings flow, or security fixes (CORS, API-key masking).
---

# Testing AIVO

AIVO = Tauri/React frontend + a FastAPI "sidecar" backend. No database; config lives in JSON files under `~` (`~/.aivo_config.json`, `~/.aivo_fleet.json`, `~/.aivo_permissions.json`, `~/.aivo_audit.jsonl`).

## Run locally
```bash
# backend (sidecar) on 127.0.0.1:8765
cd sidecar && pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8765
# frontend on localhost:5173 (separate terminal)
npm install && npm run dev
```
The frontend talks to the sidecar at `http://127.0.0.1:8765/api` (see `src/api.ts`). Open http://localhost:5173 and use the left sidebar to reach each module. Tauri desktop build is not required for testing the web UI.

## AI provider / Settings flow
- Settings page = sidebar "Settings" (`src/components/Settings/Settings.tsx`).
- Config endpoints: `GET/POST /api/ai/config` (`sidecar/modules/ai_provider.py`).
- The API key is stored server-side and **must not** be returned to the client. `GET /api/ai/config` returns `api_key_set` (bool) + `api_key_hint` (`...abcd`), never the raw `api_key`. The Settings input stays empty and shows placeholder `Saved (...abcd) — leave empty to keep`. Saving with an empty key preserves the stored key (empty = keep).
- Seed a key for tests: `curl -X POST localhost:8765/api/ai/config -H 'Content-Type: application/json' -d '{"provider":"openrouter","api_key":"sk-test-1234","model":"deepseek/deepseek-v4-flash:free"}'`.
- "Test Connection" calls `/api/ai/chat` with the stored key — needs a real provider key to succeed; a fake key returns 401.

## Security checks (curl)
```bash
curl -s localhost:8765/api/ai/config            # no api_key field; api_key_set + api_key_hint only
curl -sD- -o/dev/null -H 'Origin: http://localhost:5173' localhost:8765/api/health | grep -i access-control-allow-origin   # echoed
curl -sD- -o/dev/null -H 'Origin: https://evil.com'      localhost:8765/api/health | grep -i access-control-allow-origin   # absent = blocked
```
CORS allowlist is in `sidecar/main.py` (localhost:5173/1420, tauri://localhost; override via `AIVO_ALLOWED_ORIGINS`). Extra origins for testing: `AIVO_ALLOWED_ORIGINS=http://foo uvicorn ...`.

## Commands
- Type-check: `npx tsc -b` (works).
- Lint: `npm run lint` (oxlint). Test: `npm test` (vitest, frontend), `pytest sidecar/tests/` (backend).

## Known environment gotchas (may be fixed later)
- `npm run lint` / `npm test` / `npm run build` may fail with missing native bindings (oxlint / rolldown `*-linux-x64-gnu`). If so, `npx tsc -b` still validates TS. Bindings sometimes resolve after a clean `rm -rf node_modules && npm ci`.
- Node may warn it's below Vite's required version (20.19+/22.12+); the dev server usually still starts.
- `sidecar/tests/conftest.py` may import a non-existent symbol (`AUDIT_LOG` from `modules.audit`), breaking `pytest` collection — a pre-existing issue, not caused by your change. Verify against `main` before blaming a PR.
- Many paths/patterns are Windows-oriented (e.g. default file-search root `C:\`, `.exe` app listing); on Linux those endpoints return little but the app still runs.

## Devin Secrets Needed
- None required to run/test the UI. A real AI provider key (e.g. OpenRouter) is only needed to make "Test Connection" / AI chat succeed; masking and CORS tests need no secret.
