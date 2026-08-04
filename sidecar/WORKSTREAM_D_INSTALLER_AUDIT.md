# Workstream D — Windows Installer and Packaging Audit

## Current packaging

### Tauri front-end

- `src-tauri/tauri.conf.json` defines the Windows bundle.
- `productName`: Sentinel.
- `identifier`: `com.aivo.desktop`.
- Window size: 1280×800, minimum 900×600.
- CSP restricts remote origin access and allows local `http://127.0.0.1:8765` for the sidecar.
- Updater configured with a minisign public key and a GitHub releases endpoint.
- `bundle.resources` embeds `../sidecar/dist/sidecar.exe` at `sidecar/sidecar.exe`.

### Python sidecar

- `sidecar/sidecar.spec` is a PyInstaller spec for `sidecar/main.py`.
- It bundles the entire `../sentinel` package as data and `plugins/`.
- A large `hiddenimports` list covers FastAPI, uvicorn, Pydantic, SQLAlchemy, and sidecar packages.
- It produces `sidecar/dist/sidecar.exe`, which Tauri then bundles.

## User-data directories

- Sentinel durable data is stored in `~/.sentinel/sentinel.db` (or `%USERPROFILE%\.sentinel` on Windows).
- Legacy `~/.aivo.db` is migrated on first open.
- Logs, diagnostics and backups are stored under `~/.sentinel`.
- No data is written outside the user profile without explicit action.

## Installation states for Alpha

1. **Sentinel installed, compatible local runtime exists.**
   - Tauri installer places `Sentinel.exe` and the embedded `sidecar.exe`.
   - On first run the sidecar starts; `local_model_service` reports a usable local model.
   - User can converse immediately using local-only path.

2. **Sentinel installed, local runtime exists without model.**
   - A compatible runtime such as Ollama is installed but no model.
   - Onboarding must guide the user to download the recommended small model.
   - Cloud remains blocked until an explicit standing policy is created.

3. **Sentinel installed, no local runtime exists.**
   - Sentinel starts but `local_model_service` finds no Ollama or bundled runtime.
   - Onboarding must explain the local runtime prerequisite and offer a guided installer link.
   - Cloud remains blocked; user must explicitly choose cloud setup.

4. **Sentinel installed with explicit cloud setup.**
   - User has completed the cloud onboarding step and authorized at least one standing policy.
   - `CloudAuthorityStore` persists the policy and active execution state.
   - Costs and data sent to the provider are disclosed before use.

5. **Upgrade from earlier Sentinel/AIVO build.**
   - Tauri updater downloads the new MSI and triggers install.
   - `DatabaseManager` applies schema migrations to the existing `~/.sentinel/sentinel.db`.
   - Legacy `~/.aivo.db` is copied once if the new database does not yet exist.

6. **Uninstall while retaining user data.**
   - Standard Windows uninstaller removes `Sentinel.exe`, embedded `sidecar.exe` and program files.
   - `~/.sentinel` is left in place so conversations, preferences and audit records are preserved.

7. **Uninstall and remove user data.**
   - Optional "Remove user data" checkbox in the uninstaller.
   - When selected, `~/.sentinel` is removed after a confirmation step.

## Alpha installer requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| No manual Python installation | OK | Python is bundled inside `sidecar.exe` by PyInstaller. |
| No manual terminal commands | OK | Tauri MSI installs and launches the product. |
| No manual dependency installation | OK | Dependencies are bundled in `sidecar.exe`. |
| No editing environment files | OK | All paths and keys are discovered or prompted at runtime. |
| Local model may require guided setup | PARTIAL | Link and instructions can be shown; actual model download is out-of-band. |

## Identified packaging gaps

1. The PyInstaller `sidecar.spec` does not explicitly list the new Workstream C repository modules:
   - `sidecar.repositories.cloud_authority_store`
   - `sidecar.repositories.user_preferences_store`
   - `sidecar.repositories.data_control_store`
   - `sidecar.modules.sentinel_lifecycle`
   They may be collected transitively, but the spec should include them explicitly to avoid silent import errors in a frozen build.

2. The Tauri config still references `com.aivo.desktop` and AIVO GitHub release endpoint. For an external Alpha these should be updated to the Sentinel product identity and a controlled update channel.

3. No code-signing certificate is configured. Windows SmartScreen will block the installer unless a signed certificate is used.

4. No clean-VM validation has been performed. The D2 clean-VM checklist cannot be completed without an available Windows VM.

## Blockers

- **Windows VM access unavailable** — clean-install validation for the 12 D2 states is not performed.
- **Signing certificate unavailable** — the MSI will not pass SmartScreen on a fresh Windows account.
- **Compiled Tauri runtime unavailable in this environment** — only the source config and PyInstaller spec are auditable.
