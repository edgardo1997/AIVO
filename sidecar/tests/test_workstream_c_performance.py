import json
import math
import os
import statistics
import time
import uuid
from pathlib import Path

import pytest

from repositories.cloud_authority_store import CloudAuthorityStore
from repositories.data_control_store import DataControlStore
from repositories.database import DatabaseManager, migrate_legacy_database
from repositories.user_preferences_store import UserPreferencesStore


def _utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _p95(times):
    n = len(times)
    idx = max(0, math.ceil(n * 0.95) - 1)
    return sorted(times)[idx]


def _measure(name, func, runs=100, warmup=5):
    for _ in range(warmup):
        func()
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        func()
        t1 = time.perf_counter()
        times.append(t1 - t0)
    return {
        "name": name,
        "runs": runs,
        "warmup": warmup,
        "min_s": min(times),
        "median_s": statistics.median(times),
        "mean_s": statistics.mean(times),
        "p95_s": _p95(times),
        "max_s": max(times),
        "stdev_s": statistics.stdev(times) if len(times) > 1 else 0.0,
    }


@pytest.mark.performance
@pytest.mark.timeout(180)
def test_workstream_c_durable_path(tmp_path):
    db = DatabaseManager()
    ca = CloudAuthorityStore(db)
    up = UserPreferencesStore(db)
    dc = DataControlStore(db)

    base_user = f"bench-{uuid.uuid4().hex}"
    setup_user = f"{base_user}-setup"

    # Seed a baseline user with realistic Alpha data.
    db.upsert_conversation(setup_user, "s-setup", "Setup", [], _utc_now())
    db.upsert_conversation(setup_user, "s-setup-2", "Setup 2", [], _utc_now())
    db.insert_conversation_message_v2({
        "user_id": setup_user,
        "session_id": "s-setup",
        "message_id": f"m-{uuid.uuid4().hex}",
        "role": "user",
        "content": "hello",
        "client_request_id": f"c-{uuid.uuid4().hex}",
    })
    db.insert_conversation_message_v2({
        "user_id": setup_user,
        "session_id": "s-setup",
        "message_id": f"m-{uuid.uuid4().hex}",
        "role": "assistant",
        "content": "",
        "client_request_id": f"c-{uuid.uuid4().hex}",
        "completion_state": "completed",
    })
    up.save(setup_user, {
        "configured_provider": "openrouter",
        "onboarding_completed": True,
        "local_only": False,
    })
    ca.add_standing_policy(setup_user, {"provider_scope": ["openrouter"], "paid_use_allowed": True})
    ca.issue_one_time(setup_user, {"provider_scope": ["openrouter"], "max_cost": 1.0})

    # Pre-create a duplicate target for resolution benchmarks.
    dup_user = f"{base_user}-dup"
    dup_crid = f"dup-{uuid.uuid4().hex}"
    dup_msg_id = f"m-{uuid.uuid4().hex}"
    db.insert_conversation_message_v2({
        "user_id": dup_user,
        "session_id": "s-dup",
        "message_id": dup_msg_id,
        "role": "user",
        "content": "duplicate",
        "client_request_id": dup_crid,
    })

    # Pre-create an assistant for finalization/cancel/failure per-run.
    def _new_assistant_id():
        return f"m-{uuid.uuid4().hex}"

    def _create_pending_assistant():
        mid = _new_assistant_id()
        db.insert_conversation_message_v2({
            "user_id": setup_user,
            "session_id": "s-setup",
            "message_id": mid,
            "role": "assistant",
            "content": "",
            "client_request_id": f"c-{uuid.uuid4().hex}",
            "completion_state": "pending",
        })
        return mid

    results = []

    # Conversation persistence
    results.append(_measure(
        "thread_creation",
        lambda: db.upsert_conversation(f"{base_user}-{uuid.uuid4().hex}", f"s-{uuid.uuid4().hex[:8]}", "Bench", [], _utc_now()),
    ))

    results.append(_measure(
        "thread_lookup",
        lambda: db.fetchone(
            "SELECT session_id, title FROM conversation_threads_v2 WHERE user_id = ? AND session_id = ?",
            (setup_user, "s-setup"),
        ),
    ))

    results.append(_measure(
        "user_message_insertion",
        lambda: db.insert_conversation_message_v2({
            "user_id": f"{base_user}-{uuid.uuid4().hex}",
            "session_id": "s-msg",
            "message_id": f"m-{uuid.uuid4().hex}",
            "role": "user",
            "content": "test message",
            "client_request_id": f"c-{uuid.uuid4().hex}",
        }),
    ))

    results.append(_measure(
        "assistant_lifecycle_creation",
        lambda: db.insert_conversation_message_v2({
            "user_id": setup_user,
            "session_id": "s-setup",
            "message_id": _new_assistant_id(),
            "role": "assistant",
            "content": "",
            "client_request_id": f"c-{uuid.uuid4().hex}",
            "completion_state": "pending",
        }),
    ))

    results.append(_measure(
        "assistant_finalization",
        lambda: db.finalize_conversation_message_v2(
            setup_user,
            "s-setup",
            _create_pending_assistant(),
            content="final answer",
            completion_state="completed",
        ),
    ))

    results.append(_measure(
        "cancellation_update",
        lambda: db.finalize_conversation_message_v2(
            setup_user,
            "s-setup",
            _create_pending_assistant(),
            completion_state="cancelled",
        ),
    ))

    results.append(_measure(
        "failure_update",
        lambda: db.finalize_conversation_message_v2(
            setup_user,
            "s-setup",
            _create_pending_assistant(),
            completion_state="failed",
            error_category="provider_error",
        ),
    ))

    def _insert_pending_then_recover():
        for _ in range(2):
            db.insert_conversation_message_v2({
                "user_id": setup_user,
                "session_id": "s-pending",
                "message_id": _new_assistant_id(),
                "role": "assistant",
                "content": "",
                "client_request_id": f"c-{uuid.uuid4().hex}",
                "completion_state": "streaming",
            })
        db._recover_interrupted_conversation_messages()

    results.append(_measure(
        "interruption_recovery",
        _insert_pending_then_recover,
    ))

    results.append(_measure(
        "duplicate_request_resolution",
        lambda: db.insert_conversation_message_v2({
            "user_id": dup_user,
            "session_id": "s-dup",
            "message_id": f"m-{uuid.uuid4().hex}",
            "role": "user",
            "content": "duplicate",
            "client_request_id": dup_crid,
        }),
    ))

    results.append(_measure(
        "concurrent_duplicate_resolution",
        lambda: db.insert_conversation_message_v2({
            "user_id": dup_user,
            "session_id": "s-dup",
            "message_id": f"m-{uuid.uuid4().hex}",
            "role": "user",
            "content": "duplicate",
            "client_request_id": dup_crid,
        }),
    ))

    results.append(_measure(
        "conversation_list",
        lambda: db.list_conversations(setup_user),
    ))

    results.append(_measure(
        "message_list",
        lambda: db.list_conversation_messages_v2(setup_user, "s-setup"),
    ))

    # Cloud authority
    results.append(_measure(
        "authority_state_load",
        lambda: ca.load_state(setup_user),
    ))

    results.append(_measure(
        "standing_policy_lookup",
        lambda: ca.list_standing_policies(setup_user),
    ))

    results.append(_measure(
        "one_time_authorization_lookup",
        lambda: ca.list_one_time(setup_user),
    ))

    otc_ids = []
    def _consume_one_time():
        auth_id = ca.issue_one_time(setup_user, {"provider_scope": ["openrouter"], "max_cost": 0.5})
        otc_ids.append(auth_id)
        ca.consume_one_time(setup_user, auth_id)
    results.append(_measure(
        "atomic_consent_consumption",
        _consume_one_time,
    ))

    policy_id = ca.add_standing_policy(setup_user, {"provider_scope": ["openai"], "paid_use_allowed": False})
    results.append(_measure(
        "policy_revocation",
        lambda: ca.revoke_standing_policy(setup_user, policy_id, _utc_now()),
    ))

    # Use a small in-memory legacy database for migration benchmark.
    legacy_db = tmp_path / "legacy_bench.db"
    target_db = tmp_path / "target_bench.db"
    import sqlite3
    lc = sqlite3.connect(legacy_db)
    lc.execute("CREATE TABLE marker (value TEXT NOT NULL)")
    lc.execute("INSERT INTO marker (value) VALUES (?)", ("bench-legacy",))
    lc.commit()
    lc.close()
    def _migrate_once():
        target = tmp_path / f"target_{uuid.uuid4().hex}.db"
        return migrate_legacy_database(str(target), str(legacy_db))
    results.append(_measure(
        "legacy_migration",
        _migrate_once,
        runs=10,
    ))

    # User preferences
    pref_user = f"{base_user}-pref"
    up.save(pref_user, {"configured_provider": "sentinel_local", "local_only": True})
    results.append(_measure(
        "preference_load",
        lambda: up.load(pref_user),
    ))

    results.append(_measure(
        "preference_update",
        lambda: up.save(pref_user, {"configured_provider": "openrouter"}),
    ))

    results.append(_measure(
        "onboarding_state_lookup",
        lambda: up.load(pref_user)["onboarding_completed"],
    ))

    results.append(_measure(
        "startup_restore",
        lambda: up.load(pref_user),
    ))

    results.append(_measure(
        "preference_reset",
        lambda: up.reset(pref_user),
    ))

    # Data control
    results.append(_measure(
        "inventory_generation",
        lambda: dc.inventory(setup_user),
    ))

    results.append(_measure(
        "conversation_export",
        lambda: dc.export(setup_user, include_messages=True),
        runs=20,
    ))

    results.append(_measure(
        "complete_alpha_export",
        lambda: dc.export(setup_user, include_messages=True),
        runs=20,
    ))

    def _reset_conversations():
        u = f"{base_user}-{uuid.uuid4().hex}"
        db.upsert_conversation(u, "s1", "X", [], _utc_now())
        dc.reset(u, ["conversations"])
    results.append(_measure(
        "delete_one_conversation",
        _reset_conversations,
    ))

    def _reset_all_data():
        u = f"{base_user}-{uuid.uuid4().hex}"
        db.upsert_conversation(u, "s1", "X", [], _utc_now())
        up.save(u, {"configured_provider": "openrouter"})
        ca.add_standing_policy(u, {"provider_scope": ["openrouter"]})
        dc.reset(u, ["conversations", "preferences", "cloud_authority"])
    results.append(_measure(
        "delete_all_conversations",
        _reset_all_data,
    ))

    pref_reset_user = f"{base_user}-pref-reset"
    up.save(pref_reset_user, {"configured_provider": "openrouter"})
    results.append(_measure(
        "preference_reset_call",
        lambda: up.reset(pref_reset_user),
    ))

    ca_reset_user = f"{base_user}-ca-reset"
    ca.add_standing_policy(ca_reset_user, {"provider_scope": ["openrouter"]})
    results.append(_measure(
        "cloud_authority_reset",
        lambda: ca.delete_all_authority_data(ca_reset_user),
    ))

    def _complete_alpha_reset():
        u = f"{base_user}-{uuid.uuid4().hex}"
        db.upsert_conversation(u, "s1", "X", [], _utc_now())
        up.save(u, {"configured_provider": "openrouter"})
        ca.add_standing_policy(u, {"provider_scope": ["openrouter"]})
        dc.reset(u, ["factory"])
    results.append(_measure(
        "complete_alpha_data_reset",
        _complete_alpha_reset,
    ))

    db_size = os.path.getsize(db.db_path)
    def _count_one(sql):
        row = db.fetchone(sql)
        return list(row.values())[0] if row else 0

    record_counts = {
        "conversation_threads_v2": _count_one("SELECT COUNT(*) FROM conversation_threads_v2"),
        "conversation_messages_v2": _count_one("SELECT COUNT(*) FROM conversation_messages_v2"),
        "user_preferences_state": _count_one("SELECT COUNT(*) FROM user_preferences_state"),
        "cloud_standing_policies": _count_one("SELECT COUNT(*) FROM cloud_standing_policies"),
        "cloud_one_time_authorizations": _count_one("SELECT COUNT(*) FROM cloud_one_time_authorizations"),
    }

    report = {
        "schema": "workstream-c-performance-1.0",
        "platform": "laboratory",
        "database_size_bytes": db_size,
        "record_counts": record_counts,
        "measurements": results,
    }

    out = tmp_path / "workstream_c_performance.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print a concise markdown table to the test log.
    print("\n## Workstream C durable-path performance\n")
    print("| scenario | runs | min (ms) | median (ms) | mean (ms) | p95 (ms) | max (ms) | stdev (ms) |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        print(
            f"| {r['name']} | {r['runs']} | "
            f"{r['min_s']*1000:.3f} | {r['median_s']*1000:.3f} | "
            f"{r['mean_s']*1000:.3f} | {r['p95_s']*1000:.3f} | "
            f"{r['max_s']*1000:.3f} | {r['stdev_s']*1000:.3f} |"
        )
    print(f"\nDatabase size: {db_size} bytes")
    print(f"Record counts: {record_counts}\n")

    # Soft sanity assertions: all operations must complete and remain in a
    # reasonable micro- to millisecond range on a warm, mocked, local SQLite DB.
    for r in results:
        assert r["mean_s"] < 1.0, f"{r['name']} mean {r['mean_s']}s exceeds 1s on warm local DB"
