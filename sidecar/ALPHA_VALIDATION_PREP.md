# Alpha User Validation Preparation

## Target validation group

At least three privacy-conscious technical individuals who can install a Windows application, use a local or cloud AI, and perform a governed file action.

## Build instructions

1. Install Rust and Tauri prerequisites on a Windows build machine.
2. `cd sidecar && pyinstaller sidecar.spec` to produce `sidecar/dist/sidecar.exe`.
3. `npm install` at the repository root.
4. `npm run tauri build` to produce the MSI in `src-tauri/target/release/bundle/msi`.
5. Sign the MSI with a valid code-signing certificate before distribution.

## Known limitations

- Sentinel is an Alpha product.
- Local AI requires a compatible local runtime (e.g., Ollama) and a small model.
- Cloud AI requires explicit per-provider standing policy and one-time consent.
- Windows SmartScreen will warn about an unsigned installer.
- Clean-VM validation has not been performed in this environment.
- The full `pytest -q` suite currently has 23 pre-existing failures outside Workstream C.

## Privacy disclosure

- Conversations, preferences and cloud authority state are stored locally in `~/.sentinel/sentinel.db`.
- API keys and tokens are never written to the conversation, preference or authority stores.
- Cloud prompts are sent only to a provider the user has explicitly authorized.
- Audit and diagnostic logs are retained locally for security review.

## Feedback template

1. Installation experience: did the installer work without manual steps?
2. First run: was the Alpha status and local/cloud state clear?
3. Conversation: did the local model respond without unexpected cloud use?
4. Governed file action: was confirmation required before execution?
5. Result: could you verify the action was performed?
6. Cancel: could you cancel a stream before it completed?
7. Restart: was your conversation history preserved?
8. Export/delete: could you inspect and reset your data?
9. Trust: did you understand what Sentinel did and why?

## Bug report template

- Sentinel version and build.
- Windows version and local runtime (if any).
- Steps to reproduce.
- Expected behavior.
- Observed behavior.
- Relevant log snippet (with secrets redacted).

## Demo checklist

- [ ] Sentinel installs from MSI.
- [ ] Onboarding explains Alpha, local status and cloud options.
- [ ] User starts a conversation using local AI.
- [ ] User asks: "Find the latest PDF in my Downloads, copy it into a new folder called Reviewed, and open the copy."
- [ ] Sentinel requests confirmation.
- [ ] User approves and the copy is made.
- [ ] Sentinel verifies the copy and application launch.
- [ ] Audit record is available.
- [ ] User cancels a stream and the state becomes cancelled.
- [ ] After restart, conversation history is preserved.
- [ ] User exports or inspects data without secrets.
- [ ] User resets preferences and cloud authority.
- [ ] Sentinel shuts down without orphan processes.
- [ ] Uninstall leaves data or removes it according to user choice.

## Rollback and recovery

- Sentinel keeps a rolling SQLite WAL. A corrupt database can be restored from the most recent `-wal` or backup if one exists.
- User data in `~/.sentinel` can be copied before uninstall.
- To reset all state, use the data-control `reset` endpoint with the `factory` scope.
- To downgrade, install an older release and let the updater or installer replace the binary.

## Manual gate record-keeping

For each validator, record:

- Windows version and hardware profile.
- Local runtime and model, if any.
- Cloud provider used, if any.
- Confirmation and cancel paths completed.
- Export/delete performed.
- Restart persistence verified.
- Final trust rating (1–5).
