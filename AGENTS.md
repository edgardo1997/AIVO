# Test Commands

- **JS tests**: `npm test` (vitest run)
- **Python tests (all)**: `cd sidecar && python -m pytest`
- **Python tests (specific file)**: `cd sidecar && python -m pytest tests/test_agents.py`
- **Python tests (specific class)**: `cd sidecar && python -m pytest tests/test_agents.py::TestAgentTools`
- **Python tests (unit only)**: `cd sidecar && python -m pytest -m unit`
- **Python tests (integration)**: `cd sidecar && python -m pytest -m integration`
- **Python tests (security)**: `cd sidecar && python -m pytest -m security`
- **Python tests (e2e)**: `cd sidecar && python -m pytest -m e2e`
- **Python tests (performance)**: `cd sidecar && python -m pytest -m performance --timeout=180`
