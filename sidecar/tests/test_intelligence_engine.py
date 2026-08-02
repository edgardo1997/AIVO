from sentinel.intelligence.engine import IntelligenceEngine


class _Capabilities:
    def get_capabilities(self, task_type):
        return ["chat"]

    def get_model_capabilities(self, model_id):
        return ["chat"]


class _Discovery:
    def list_models(self):
        return ["sentinel-local"]


def test_sync_recommend_uses_the_selection_pipeline():
    engine = IntelligenceEngine(
        capability_engine=_Capabilities(),
        model_discovery=_Discovery(),
    )

    recommendation = engine.recommend("quick", required_capabilities=["chat"])

    assert recommendation.model_id == "sentinel-local"
    assert recommendation.reasoning != "Sync recommend deprecated — use await recommend_async"
