from typing import Any, Dict, List, Optional
import time


class E2EAssertions:
    @staticmethod
    def assert_success(result: Dict[str, Any], msg: str = "Expected success") -> None:
        assert result.get("success", False), f"{msg}: {result.get('error', 'no error message')}"

    @staticmethod
    def assert_response_contains(data: Dict[str, Any], key: str, expected_type: type, msg: str = "") -> None:
        val = data.get(key)
        assert val is not None, f"Missing key '{key}' in response data. {msg}"
        assert isinstance(val, expected_type), f"Key '{key}' should be {expected_type.__name__}, got {type(val).__name__}. {msg}"

    @staticmethod
    def assert_intent_detected(data: Dict[str, Any], expected_category: str) -> None:
        intent_str = data.get("intent", "")
        assert intent_str, "No intent in response data"
        assert expected_category.lower() in intent_str.lower(), f"Expected intent category '{expected_category}' not found in '{intent_str}'"

    @staticmethod
    def assert_decision_allowed(data: Dict[str, Any]) -> None:
        decision_str = str(data.get("decision", ""))
        assert "APPROVE" in decision_str or "ALLOW" in decision_str, f"Decision was not approved: {decision_str}"

    @staticmethod
    def assert_plan_has_steps(data: Dict[str, Any], min_steps: int = 1) -> None:
        plan_str = str(data.get("plan", ""))
        assert plan_str, "No plan in response data"
        results = data.get("results", [])
        assert len(results) >= min_steps, f"Expected at least {min_steps} execution steps, got {len(results)}"

    @staticmethod
    def assert_no_direct_gateway(data: Dict[str, Any]) -> None:
        results = data.get("results", [])
        for r in results:
            result_obj = r.get("result", {})
            if hasattr(result_obj, "success"):
                assert result_obj.success is not None
        audit = data.get("audit_log", [])
        has_approval = any(
            entry.get("approved", False) or entry.get("result") == "success"
            for entry in (audit if isinstance(audit, list) else [])
        )
        if not has_approval:
            decision_str = str(data.get("decision", ""))
            assert "APPROVE" in decision_str, f"No approval in audit or decision: {decision_str[:200]}"

    @staticmethod
    def assert_session_created(memory: Any, session_id: str) -> None:
        if memory is None:
            return
        session = memory.get_session(session_id) if hasattr(memory, "get_session") else None
        assert session is not None, f"Session '{session_id}' was not created"

    @staticmethod
    def assert_message_saved(memory: Any, session_id: str, expected_text: str) -> None:
        if memory is None:
            return
        history = memory.get_session_history(session_id, limit=10, user_id="test") if hasattr(memory, "get_session_history") else []
        texts = [str(r) for r in (history if isinstance(history, list) else [])]
        combined = " ".join(texts)
        assert expected_text.lower() in combined.lower() or not expected_text, f"Expected text '{expected_text}' not found in session history"

    @staticmethod
    def assert_hardware_detected(data: Dict[str, Any], components: List[str]) -> None:
        system_str = str(data.get("system", ""))
        for comp in components:
            assert comp.lower() in system_str.lower(), f"Hardware component '{comp}' not detected in system context: {system_str[:200]}"
        context = data.get("context", {})
        system_ctx = context.get("system", "")
        if system_ctx:
            for comp in components:
                assert comp.lower() in str(system_ctx).lower(), f"Hardware component '{comp}' not in context.system"

    @staticmethod
    def assert_profile_activated(data: Dict[str, Any], profile: str) -> None:
        results = data.get("results", [])
        profile_str = " ".join(str(r) for r in results)
        assert profile.lower() in profile_str.lower(), f"Profile '{profile}' not found in execution results"

    @staticmethod
    def assert_rollback_available(data: Dict[str, Any]) -> None:
        results = data.get("results", [])
        snapshot_found = any("snapshot" in str(r.get("result", "")).lower() for r in results)
        plan_str = str(data.get("plan", ""))
        assert snapshot_found or "snapshot" in plan_str.lower(), "No snapshot/rollback mechanism found in plan or results"

    @staticmethod
    def assert_project_context_restored(data: Dict[str, Any], project: str) -> None:
        plan_str = str(data.get("plan", ""))
        intent_str = str(data.get("intent", ""))
        combined = f"{plan_str} {intent_str}"
        assert project.lower() in combined.lower(), f"Project context '{project}' not found in plan or intent"

    @staticmethod
    def assert_metrics(pipeline_metrics: Dict[str, float], thresholds: Dict[str, float]) -> None:
        for key, max_val in thresholds.items():
            actual = pipeline_metrics.get(key, 0)
            assert actual <= max_val, f"Pipeline metric '{key}' exceeded threshold: {actual:.1f} > {max_val}"

    @staticmethod
    def assert_audit_created(data: Dict[str, Any]) -> None:
        audit = data.get("audit_log", [])
        if isinstance(audit, list):
            assert len(audit) > 0, "No audit entries found"
            assert any(e.get("action", "") for e in audit), "Audit entries missing action field"
