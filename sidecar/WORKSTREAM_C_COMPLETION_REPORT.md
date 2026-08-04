# Workstream C Completion Report

## 1. Ownership before and after

Before Workstream C, conversation persistence was split between the legacy `sentinel/storage/repositories/conversation_repository.py` and an ad-hoc v1 `conversation_threads` table. Cloud authority, user preferences and data-control had no durable store. After Workstream C, `sidecar/repositories/database.py` is the single durable owner for all of these concerns, supported by `CloudAuthorityStore`, `UserPreferencesStore` and `DataControlStore`.

## 2. Legacy repository disposition

`sentinel/storage/repositories/conversation_repository.py` is quarantined. It is no longer the active production truth; the schema-v2 path in `DatabaseManager` is authoritative. A migration is defined for `conversation_threads_v2` and `conversation_messages_v2`.

## 3. Schema v2 and migration

- Schema version 13 is current (`BASELINE_SCHEMA_VERSION = 10`, `LATEST_SCHEMA_VERSION = 13`).
- Migrations v11–v13 create the durable v2 conversation tables, cloud authority tables and user preference store.
- `DatabaseManager` rejects databases newer than the build and applies migrations idempotently.

## 4. Write ownership and idempotency

- `DatabaseManager.insert_conversation_message_v2` uses `client_request_id` and `correlation_id` as idempotency keys with a unique index.
- User messages, assistant finalization, cancellation and failure are inserted exactly once.
- `tests/test_conversation_idempotency.py` and `tests/test_conversation_recovery.py` cover the invariants.

## 5. Streaming lifecycle

- Streaming assistant messages are created in `streaming` state and finalized to `completed` once.
- Cancellation and failure produce terminal states that are immutable to subsequent updates.
- Token generation does not perform database writes.

## 6. Restart/interruption recovery

- `DatabaseManager._recover_interrupted_conversation_messages` marks `pending` and `streaming` messages as `interrupted` on startup.
- Interrupted messages do not regenerate automatically.
- `tests/test_conversation_recovery.py` validates the behavior.

## 7. CloudAuthority persistence

- `CloudAuthorityStore` owns state, standing policies and one-time authorizations in SQLite.
- Standing policies survive restart; one-time consents are consumed atomically and cannot be replayed.
- `tests/test_cloud_authority_persistence.py` covers all invariants.

## 8. Preference persistence

- `UserPreferencesStore` is the single owner for user preferences and active execution state.
- Invalid combinations are rejected; reset restores safe defaults.
- `tests/test_user_preferences_persistence.py` validates restart survival and recompute truthfulness.

## 9. Inspect/export/delete/reset contract

- `DataControlStore` supports `inventory`, `export` and scoped `reset`.
- Export includes a manifest, redacts secrets and truthfully records retained categories.
- Reset is scoped (`conversations`, `preferences`, `cloud_authority`, `onboarding`, `factory`) and does not delete audit records or provider-side data.
- `tests/test_data_control.py` and `tests/test_alpha_conversation_export.py` cover the contract.

## 10. Test results

Targeted Workstream C suites (all pass):

- `test_legacy_conversation_quarantine.py` — passed
- `test_conversation_schema_v2.py` — passed
- `test_database_migration.py` — passed
- `test_conversation_idempotency.py` — passed
- `test_conversation_recovery.py` — passed
- `test_cloud_authority_persistence.py` — passed
- `test_user_preferences_persistence.py` — passed
- `test_data_control.py` — passed
- `test_alpha_conversation_export.py` — passed
- `test_alpha_cloud_authority.py` — passed
- `test_alpha_tool_gateway_authority.py` — passed
- `test_chat_pipeline.py` — passed
- `alpha_constitutional_gate` marker — 38 passed
- `test_workstream_c_performance.py` — passed

Full `pytest -q` result:

- 3040 passed, 14 skipped, **23 failed**, 225 warnings
- Failures are outside Workstream C: `test_automations_persistence.py`, `test_fase11_closure.py`, `test_simulation_blocking.py`, `test_trust_pipeline_invariants.py`, `test_unified_confirmation.py`, `test_unified_provider_selection.py`
- Workstream C paths are green; product-wide full-suite green remains blocked by these unrelated pre-existing failures.

## 11. Performance results

`tests/test_workstream_c_performance.py` was run on the laboratory Windows profile.

Summary:

- All conversation, cloud-authority, preference and data-control operations measured in the micro- to low-millisecond range.
- Worst-case warm operation: export ~22 ms p95.
- All means below the 1 s sanity threshold on a warm, local, mocked SQLite database.
- Database size at end of benchmark: 1,232,896 bytes.
- Full numbers are recorded in `PERFORMANCE_BASELINE.md`.

## 12. Security/privacy review

- No API keys, tokens or prompts are stored in authority, preference or data-control stores.
- Export redacts secret keys, bearer tokens and patterns before returning the package.
- Reset truthfully reports retained data (audit, diagnostics, backups, provider-side data).
- Duplicate prevention, cancellation, failure and interruption states preserve evidence without fabricating completion.

## 13. Remaining Alpha blockers

- Product-wide `pytest -q` must reach zero failures before external Alpha.
- The 23 full-suite failures are pre-existing and unrelated to Workstream C, but they block the global "zero failures" gate.
- Real Tauri/WebView runtime is not available for UI-level cancel and authenticated transport validation.
- Windows clean-VM installer validation is not yet performed.

## 14. Exact readiness recommendation

Workstream C is implementation-complete and its targeted validation is green. The durable conversation, cloud-authority, preference and data-control contracts are ready for integration. **Do not declare full Workstream C complete for an external Alpha until the unrelated 23 full-suite failures are resolved and a product-wide green run is achieved.** Proceed with Workstream D for shutdown, installer, onboarding and UI integration, but keep the product-wide test failures as an explicit dependency for any Alpha release.
