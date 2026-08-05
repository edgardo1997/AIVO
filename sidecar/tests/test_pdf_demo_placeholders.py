import pytest

from sentinel.core.orchestrator import StepResult


@pytest.fixture(scope="module")
def orch():
    from modules.sentinel_bridge_helpers import get_orchestrator
    return get_orchestrator()


@pytest.fixture
def resolve(orch):
    def _resolve(params, context):
        return orch._resolve_step_params(params, context)
    return _resolve


@pytest.mark.alpha_constitutional_gate
class TestPlaceholderResolution:
    def test_resolves_parameter(self, resolve):
        context = {"parameters": {"source_dir": "~/Downloads"}, "step_results": []}
        assert resolve({"root": "{{parameters.source_dir}}"}, context) == {"root": "~/Downloads"}

    def test_resolves_step_data_scalar(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="copy", tool_id="filesystem.copy", success=True, data={"path": "C:/Reviewed/file.pdf"})
            ],
        }
        assert resolve({"path": "{{steps.copy.data.path}}"}, context) == {"path": "C:/Reviewed/file.pdf"}

    def test_resolves_step_data_list_index(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(
                    step_id="search",
                    tool_id="filesystem.search",
                    success=True,
                    data={
                        "files": [
                            {"name": "a.pdf", "path": "/a.pdf"},
                            {"name": "b.pdf", "path": "/b.pdf"},
                        ]
                    },
                )
            ],
        }
        assert resolve({"source": "{{steps.search.data.files.1.path}}"}, context) == {"source": "/b.pdf"}

    def test_missing_parameter_fails(self, resolve):
        context = {"parameters": {}, "step_results": []}
        with pytest.raises(ValueError) as exc:
            resolve({"root": "{{parameters.missing}}"}, context)
        assert "cannot resolve" in str(exc.value).lower() or "missing" in str(exc.value).lower()

    def test_missing_step_fails(self, resolve):
        context = {"parameters": {}, "step_results": []}
        with pytest.raises(ValueError) as exc:
            resolve({"source": "{{steps.copy.data.path}}"}, context)
        assert "step 'copy' not found" in str(exc.value)

    def test_missing_field_fails(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="search", tool_id="filesystem.search", success=True, data={"query": "*.pdf"})
            ],
        }
        with pytest.raises(ValueError) as exc:
            resolve({"source": "{{steps.search.data.files}}"}, context)
        assert "cannot resolve" in str(exc.value).lower()

    def test_future_step_not_available(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="search", tool_id="filesystem.search", success=True, data={"files": []})
            ],
        }
        with pytest.raises(ValueError) as exc:
            resolve({"path": "{{steps.open.data.path}}"}, context)
        assert "step 'open' not found" in str(exc.value)

    def test_circular_dependency_rejected_by_planner(self, resolve, orch):
        from sentinel.core.planner import Plan, PlanStep
        from sentinel.core.intent import Intent

        plan = Plan(
            steps=[
                PlanStep(id="a", tool_id="a.t", depends_on=["b"]),
                PlanStep(id="b", tool_id="b.t", depends_on=["a"]),
            ],
            intent=Intent(action="test", target="test"),
        )
        levels = orch._planner.resolve_dependencies(plan)
        assert levels == []

    def test_none_data_fails(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="search", tool_id="filesystem.search", success=True, data=None)
            ],
        }
        with pytest.raises(ValueError) as exc:
            resolve({"source": "{{steps.search.data.files}}"}, context)
        assert "cannot resolve" in str(exc.value).lower()

    def test_wrong_type_index_fails(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="search", tool_id="filesystem.search", success=True, data={"files": 123})
            ],
        }
        with pytest.raises(ValueError) as exc:
            resolve({"source": "{{steps.search.data.files.0.path}}"}, context)
        assert "cannot resolve" in str(exc.value).lower()

    def test_previous_step_failed_fails(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="search", tool_id="filesystem.search", success=False, data={"error": "blocked"})
            ],
        }
        with pytest.raises(ValueError) as exc:
            resolve({"source": "{{steps.search.data.files.0.path}}"}, context)
        assert "cannot resolve" in str(exc.value).lower()

    def test_path_with_spaces(self, resolve):
        context = {
            "parameters": {"source_dir": "C:/Users/Test User/My Downloads"},
            "step_results": [],
        }
        assert resolve({"root": "{{parameters.source_dir}}"}, context) == {"root": "C:/Users/Test User/My Downloads"}

    def test_path_with_unicode(self, resolve):
        context = {
            "parameters": {"source_dir": "C:/Usuarios/Año_2024/DESCARGAS"},
            "step_results": [],
        }
        assert resolve({"root": "{{parameters.source_dir}}"}, context) == {"root": "C:/Usuarios/Año_2024/DESCARGAS"}

    def test_whole_step_object_interpolation_fails(self, resolve):
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="search", tool_id="filesystem.search", success=True, data={"files": []})
            ],
        }
        with pytest.raises(ValueError) as exc:
            resolve({"x": "{{steps.search}}"}, context)
        assert "invalid step placeholder" in str(exc.value).lower()

    def test_unknown_root_fails(self, resolve):
        context = {"parameters": {}, "step_results": []}
        with pytest.raises(ValueError) as exc:
            resolve({"x": "{{context.approved_plan_grant_id}}"}, context)
        assert "unknown placeholder root" in str(exc.value).lower()

    def test_dunder_access_treated_as_key(self, resolve):
        # The resolver only does key/list access; it does not allow attribute access, so dunder keys fail as missing.
        context = {
            "parameters": {},
            "step_results": [
                StepResult(step_id="search", tool_id="filesystem.search", success=True, data={"files": []})
            ],
        }
        with pytest.raises(ValueError) as exc:
            resolve({"x": "{{steps.search.data.__class__}}"}, context)
        assert "cannot resolve" in str(exc.value).lower()
