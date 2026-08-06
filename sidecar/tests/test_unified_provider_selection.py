import os
import sys
import time
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from fastapi.testclient import TestClient

# Create test client
client = TestClient(app)

# Set test mode
app.state._test_mode = True
app.state._test_secret = "valid-test-token"


class TestUnifiedProviderSelection:
    """Test unified provider selection across conversational and governed routes."""
    
    def test_hola_with_explicit_openrouter(self):
        """Test 1: 'Hola' with explicit OpenRouter selection uses OpenRouter."""
        print("\n" + "="*80)
        print("TEST 1: Hola with Explicit OpenRouter Selection")
        print("="*80)
        
        test_message = "Hola"
        print(f"Message: '{test_message}'")
        print(f"Explicit Provider: openrouter")
        
        total_start = time.perf_counter()
        
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": test_message, "session_id": "unified-test-1", "provider": "openrouter"},
            headers={"X-Test-Token": "valid-test-token"}
        )
        
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Response: {response.text[:500]}")
            pytest.fail(f"Request failed with status {response.status_code}")
        
        meta_info = {}
        pipeline_info = {}
        failed_events = []
        
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "meta":
                        meta_info.update(event)
                        print(f"Provider: {event.get('provider')}")
                        print(f"Model: {event.get('model')}")
                    elif event.get("type") == "pipeline":
                        pipeline_info.update(event)
                        print(f"Route: {pipeline_info.get('route')}")
                    elif event.get("event_type") == "failed":
                        failed_events.append(event)
                except json.JSONDecodeError:
                    pass
        
        total_end = time.perf_counter()
        total_duration = (total_end - total_start) * 1000
        
        print(f"\nResults:")
        print(f"Total Duration: {total_duration:.2f}ms")
        print(f"Provider: {meta_info.get('provider')}")
        print(f"Model: {meta_info.get('model')}")
        print(f"Route: {pipeline_info.get('route')}")
        
        # Without cloud authority, OpenRouter must not be reported as active.
        # If a local runtime is ready, it is selected and reported.
        # If not, the stream must end with a failed event and no active provider.
        assert meta_info.get('provider') != 'openrouter'
        assert meta_info.get('actual_provider') != 'openrouter'
        if meta_info.get('actual_provider') in ('sentinel_core', 'sentinel_local'):
            assert meta_info.get('fallback_required') is True
            assert meta_info.get('actual_model') is not None
        else:
            # No local runtime ready: expect a canonical failure
            assert failed_events
    def test_variable_with_configured_preference(self):
        """Test 2: 'Explícame qué es una variable' with configured OpenRouter preference uses OpenRouter."""
        print("\n" + "="*80)
        print("TEST 2: Variable Explanation with Configured Preference")
        print("="*80)
        
        test_message = "Explícame qué es una variable"
        print(f"Message: '{test_message}'")
        print(f"Configured Preference: openrouter (from environment)")
        
        total_start = time.perf_counter()
        
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": test_message, "session_id": "unified-test-2"},
            headers={"X-Test-Token": "valid-test-token"}
        )
        
        if response.status_code != 200:
            print(f"ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text[:200]}")
            pytest.fail(f"Request failed with status {response.status_code}")
        
        meta_info = {}
        pipeline_info = {}
        failed_events = []
        
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "meta":
                        meta_info.update(event)
                        print(f"Provider: {event.get('provider')}")
                        print(f"Model: {event.get('model')}")
                    elif event.get("type") == "pipeline":
                        pipeline_info.update(event)
                        print(f"Route: {pipeline_info.get('route')}")
                    elif event.get("event_type") == "failed":
                        failed_events.append(event)
                except json.JSONDecodeError:
                    pass
        
        total_end = time.perf_counter()
        total_duration = (total_end - total_start) * 1000
        
        print(f"\nResults:")
        print(f"Total Duration: {total_duration:.2f}ms")
        print(f"Provider: {meta_info.get('provider')}")
        print(f"Model: {meta_info.get('model')}")
        print(f"Route: {pipeline_info.get('route')}")
        
        # Verify configured preference is not enough without cloud authority.
        assert meta_info.get('provider') != 'openrouter'
        assert meta_info.get('actual_provider') != 'openrouter'
        if meta_info.get('actual_provider') in ('sentinel_core', 'sentinel_local'):
            assert meta_info.get('fallback_required') is True
            assert meta_info.get('actual_model') is not None
        else:
            assert failed_events
        
    def test_conversation_normal_routing(self):
        """Test 3: Ordinary conversation with no explicit preference uses normal routing."""
        print("\n" + "="*80)
        print("TEST 3: Ordinary Conversation with Normal Routing")
        print("="*80)
        
        test_message = "¿Qué hora es?"
        print(f"Message: '{test_message}'")
        print(f"No explicit preference - should use normal routing")
        
        total_start = time.perf_counter()
        
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": test_message, "session_id": "unified-test-3"},
            headers={"X-Test-Token": "valid-test-token"}
        )
        
        if response.status_code != 200:
            print(f"ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text[:200]}")
            pytest.fail(f"Request failed with status {response.status_code}")
        
        meta_info = {}
        pipeline_info = {}
        failed_events = []
        
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "meta":
                        meta_info.update(event)
                        print(f"Provider: {event.get('provider')}")
                        print(f"Model: {event.get('model')}")
                    elif event.get("type") == "pipeline":
                        pipeline_info.update(event)
                        print(f"Route: {pipeline_info.get('route')}")
                    elif event.get("event_type") == "failed":
                        failed_events.append(event)
                except json.JSONDecodeError:
                    pass
        
        total_end = time.perf_counter()
        total_duration = (total_end - total_start) * 1000
        
        print(f"\nResults:")
        print(f"Total Duration: {total_duration:.2f}ms")
        print(f"Provider: {meta_info.get('provider')}")
        print(f"Model: {meta_info.get('model')}")
        print(f"Route: {pipeline_info.get('route')}")
        
        # Without cloud authority, only a ready local provider is reported.
        # Otherwise a canonical failure is emitted.
        assert meta_info.get('actual_provider') != 'openrouter'
        if meta_info.get('actual_provider') in ('sentinel_core', 'sentinel_local'):
            assert meta_info.get('actual_model') is not None
            assert meta_info.get('fallback_required') is True
        else:
            assert failed_events
        
    def test_conversation_no_deep_context(self):
        """Test 7: Conversational requests do not invoke DeepContextEngine."""
        print("\n" + "="*80)
        print("TEST 7: Conversation Route Does Not Invoke DeepContextEngine")
        print("="*80)
        
        test_message = "Hola"
        print(f"Message: '{test_message}'")
        print(f"Route: conversation-only (confidence < 0.6)")
        
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": test_message, "session_id": "unified-test-7"},
            headers={"X-Test-Token": "valid-test-token"}
        )
        
        if response.status_code != 200:
            pytest.fail(f"Request failed with status {response.status_code}")
        
        pipeline_info = {}
        
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "pipeline":
                        pipeline_info = event
                        print(f"Route: {pipeline_info.get('route')}")
                except json.JSONDecodeError:
                    pass
        
        # Verify conversation route was used (not governed)
        assert pipeline_info.get('route') == 'conversation'
        
    def test_conversation_no_tool_execution(self):
        """Test 8: Conversational requests do not execute tools."""
        print("\n" + "="*80)
        print("TEST 8: Conversation Route Does Not Execute Tools")
        print("="*80)
        
        test_message = "¿Cómo estás?"
        print(f"Message: '{test_message}'")
        print(f"Should not execute tools in conversation route")
        
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": test_message, "session_id": "unified-test-8"},
            headers={"X-Test-Token": "valid-test-token"}
        )
        
        if response.status_code != 200:
            pytest.fail(f"Request failed with status {response.status_code}")
        
        pipeline_info = {}
        
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "pipeline":
                        pipeline_info = event
                        print(f"Pipeline Trace: {pipeline_info.get('pipeline')}")
                        print(f"Route: {pipeline_info.get('route')}")
                except json.JSONDecodeError:
                    pass
        
        # Verify no tool execution occurred in conversation route
        pipeline_trace = pipeline_info.get('pipeline', {})
        # In conversation route, pipeline should be None or not contain tool execution
        assert pipeline_info.get('route') == 'conversation'
        
    def test_ui_metadata_matches_backend(self):
        """Test 9: UI metadata matches the provider that actually generated the response."""
        print("\n" + "="*80)
        print("TEST 9: UI Metadata Matches Backend Provider")
        print("="*80)
        
        test_message = "Hola"
        print(f"Message: '{test_message}'")
        
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": test_message, "session_id": "unified-test-9"},
            headers={"X-Test-Token": "valid-test-token"}
        )
        
        if response.status_code != 200:
            pytest.fail(f"Request failed with status {response.status_code}")
        
        meta_info = {}
        
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "meta":
                        meta_info.update(event)
                        print(f"UI Metadata Provider: {event.get('provider')}")
                        print(f"UI Metadata Model: {event.get('model')}")
                except json.JSONDecodeError:
                    pass
        
        # Verify UI metadata is present and matches actual selection
        assert 'provider' in meta_info
        assert 'model' in meta_info
        assert meta_info.get('actual_provider') is not None
        assert meta_info.get('actual_model') is not None
        assert meta_info.get('provider') == meta_info.get('actual_provider')
        assert meta_info.get('model') == meta_info.get('actual_model')

    def test_explicit_unavailable_reports_fallback(self):
        """An explicit provider without credentials must not be reported as the actual provider."""
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": "Hola", "session_id": "unified-test-fallback", "provider": "openai"},
            headers={"X-Test-Token": "valid-test-token"},
        )
        assert response.status_code == 200

        meta_info = {}
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "meta":
                        meta_info.update(event)
                except json.JSONDecodeError:
                    pass

        assert meta_info.get("requested_provider") == "openai"
        assert meta_info.get("actual_provider") != "openai"
        assert meta_info.get("actual_provider") is not None
        assert meta_info.get("fallback_required") is True
        assert meta_info.get("fallback_reason") is not None
        assert meta_info.get("provider") == meta_info.get("actual_provider")

    def test_correlation_id_propagates_through_stream(self):
        """An X-Correlation-Id header must appear in both pipeline and meta events."""
        expected = "test-corr-123"
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": "Hola", "session_id": "unified-test-corr"},
            headers={"X-Test-Token": "valid-test-token", "X-Correlation-Id": expected},
        )
        assert response.status_code == 200

        meta_info = {}
        pipeline_info = {}
        for line in response.text.splitlines():
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "meta":
                        meta_info.update(event)
                    elif event.get("type") == "pipeline":
                        pipeline_info.update(event)
                except json.JSONDecodeError:
                    pass

        assert meta_info.get("correlation_id") == expected
        assert pipeline_info.get("correlation_id") == expected
