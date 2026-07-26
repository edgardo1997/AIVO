from copy import deepcopy
from datetime import datetime, timezone

from sentinel.runtime_v2_controlled import (
    RuntimeShadowResultV1,
    RuntimeV2Control,
    RuntimeV2Router,
)


def _result() -> RuntimeShadowResultV1:
    return RuntimeShadowResultV1(
        schema_version="1.0",
        correlation_id="shadow_test",
        timestamp=datetime.now(timezone.utc),
        legacy_status="COMPLETED",
        shadow_status="OBSERVED",
        authority=False,
    )


def test_routing_disabled_does_not_call_shadow():
    called = False

    def shadow(_event):
        nonlocal called
        called = True
        return _result()

    event = {"nested": {"value": 1}}
    result = RuntimeV2Router(RuntimeV2Control()).route(
        event,
        shadow_handler=shadow,
    )
    assert called is False
    assert result.shadow_status == "DISABLED"
    assert result.authority is False


def test_routing_shadow_active():
    router = RuntimeV2Router(RuntimeV2Control(routing_enabled=True))
    result = router.route(
        {"event": "intent"},
        shadow_handler=lambda _event: _result(),
    )
    assert result.shadow_status == "OBSERVED"
    assert result.authority is False


def test_router_uses_deep_copy_and_preserves_legacy():
    event = {"nested": {"values": [1, 2, 3]}}
    before = deepcopy(event)
    received = None

    def shadow(copied):
        nonlocal received
        received = copied
        copied["nested"]["values"].append(4)
        return _result()

    RuntimeV2Router(RuntimeV2Control(routing_enabled=True)).route(event, shadow_handler=shadow)
    assert event == before
    assert received is not event
    assert received["nested"] is not event["nested"]


def test_router_isolates_shadow_failure():
    event = {"status": "legacy-ok"}

    def failing(_event):
        raise RuntimeError("private shadow failure")

    result = RuntimeV2Router(RuntimeV2Control(routing_enabled=True)).route(event, shadow_handler=failing)
    assert event == {"status": "legacy-ok"}
    assert result.shadow_status == "ERROR"
    assert result.errors == ("shadow_routing_failure",)
    assert "private shadow failure" not in result.model_dump_json()
