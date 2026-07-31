import argparse
import asyncio
import json
import sys
from typing import Any, Dict, List, Optional


def _get_registry():
    _get_intelligence()
    from modules import get_model_registry

    return get_model_registry()


_cli_intel = None
_cli_engine = None


def _get_intelligence():
    global _cli_intel, _cli_engine
    if _cli_intel is not None:
        return _cli_intel
    from modules import get_capability_engine, get_model_registry
    from sentinel.core.intelligence_coordinator import IntelligenceCoordinator
    from sentinel.storage.repositories.model_repository import ModelRepository

    _cli_intel = IntelligenceCoordinator(
        model_registry=get_model_registry(),
        capability_engine=get_capability_engine(),
    )
    try:
        _cli_engine = asyncio.run(_open_storage())
        _cli_intel.set_model_repository(ModelRepository(_cli_engine))
        from sentinel.storage.repositories.feedback_repository import FeedbackRepository
        from sentinel.storage.repositories.model_performance_repository import ModelPerformanceRepository
        from sentinel.storage.repositories.execution_repository import ExecutionRepository
        from sentinel.storage.repositories.user_preference_repository import UserPreferenceRepository

        _cli_intel.set_feedback_repository(FeedbackRepository(_cli_engine))
        _cli_intel.set_model_performance_repository(ModelPerformanceRepository(_cli_engine))
        _cli_intel.set_execution_repository(ExecutionRepository(_cli_engine))
        _cli_intel.set_user_preference_repository(UserPreferenceRepository(_cli_engine))
        asyncio.run(_cli_intel.load_registry_from_repository())
        asyncio.run(_cli_intel.recover_learning())
    except Exception:
        _cli_engine = None
    return _cli_intel


async def _open_storage():
    from sentinel.storage import StorageEngine

    engine = StorageEngine()
    await engine.initialize()
    return engine


def _persist() -> None:
    if _cli_intel is None:
        _get_intelligence()
    if _cli_engine is None:
        return
    try:
        asyncio.run(_cli_intel.persist_registry_to_repository())
    except Exception:
        pass


def _delete_from_repo(model_id: str) -> None:
    if _cli_intel is None:
        _get_intelligence()
    if _cli_engine is None:
        return
    repo = getattr(_cli_intel, "_model_repo", None)
    if repo is None:
        return
    try:
        asyncio.run(repo.delete(model_id))
    except Exception:
        pass


def _close() -> None:
    global _cli_engine
    if _cli_engine is None:
        return
    try:
        asyncio.run(_cli_engine.close())
    except Exception:
        pass
    _cli_engine = None


def _model_to_dict(model: Any) -> Dict[str, Any]:
    return {
        "id": model.id,
        "provider": model.provider,
        "context_window": model.context_window,
        "capabilities": sorted(
            c
            for c in (
                "tool_calling" if model.supports_tool_calling else None,
                "vision" if model.supports_vision else None,
                "coding" if model.supports_coding else None,
                "reasoning" if model.supports_reasoning else None,
                "embeddings" if model.supports_embeddings else None,
                "local" if model.local else None,
            )
            if c
        ),
        "speed": model.speed,
        "cost": model.cost,
        "local": model.local,
        "status": getattr(model.status, "value", str(model.status)),
        "description": model.description,
        "tags": list(model.tags),
        "display_name": model.display_name,
    }


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_list(args: argparse.Namespace) -> int:
    registry = _get_registry()
    models = registry.list_all()
    if args.provider:
        models = [m for m in models if m.provider == args.provider]
    if args.capability:
        models = [m for m in models if m.has_capability(args.capability)]
    if args.status:
        models = [m for m in models if getattr(m.status, "value", str(m.status)) == args.status]
    _print([_model_to_dict(m) for m in models])
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    model = _get_registry().get(args.model_id)
    if model is None:
        print(f"Model '{args.model_id}' not found", file=sys.stderr)
        return 1
    _print(_model_to_dict(model))
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    from sentinel.models import ModelMetadata, ModelStatus

    registry = _get_registry()
    if registry.get(args.model_id) is not None:
        print(f"Model '{args.model_id}' already registered", file=sys.stderr)
        return 1
    model = ModelMetadata(
        id=args.model_id,
        provider=args.provider,
        context_window=args.context_window,
        supports_tool_calling=args.tool_calling,
        supports_vision=args.vision,
        supports_coding=args.coding,
        supports_reasoning=args.reasoning,
        supports_embeddings=args.embeddings,
        speed=args.speed,
        cost=args.cost,
        local=args.local,
        status=ModelStatus.AVAILABLE,
        description=args.description,
        tags=args.tags,
    )
    registry.upsert(model)
    _persist()
    _print({"status": "registered", "model_id": args.model_id})
    return 0


def cmd_unregister(args: argparse.Namespace) -> int:
    registry = _get_registry()
    if registry.get(args.model_id) is None:
        print(f"Model '{args.model_id}' not found", file=sys.stderr)
        return 1
    registry.unregister(args.model_id)
    _delete_from_repo(args.model_id)
    _persist()
    _print({"status": "unregistered", "model_id": args.model_id})
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    intel = _get_intelligence()
    recommendation = intel.recommend_model(args.task)
    _print(recommendation.to_dict())
    return 0


def cmd_strategy(args: argparse.Namespace) -> int:
    intel = _get_intelligence()
    strategy = intel.decide_strategy(args.task)
    _print(strategy.to_dict())
    return 0


def cmd_rankings(args: argparse.Namespace) -> int:
    intel = _get_intelligence()
    rankings = intel.get_rankings(task_type=args.task_type, top_k=args.top_k)
    _print([s.to_dict() for s in rankings])
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    intel = _get_intelligence()
    result = asyncio.run(intel.discover_models())
    _persist()
    _print({"status": "ok", "discovery": result})
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    intel = _get_intelligence()
    result = asyncio.run(intel.health_check_models())
    _print(result)
    return 0


def cmd_learning_memory(args: argparse.Namespace) -> int:
    intel = _get_intelligence()
    result = asyncio.run(intel.learning_memory_status())
    _print(result)
    return 0


def _add_common_filters(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--provider", default=None, help="Filter by provider id")
    sp.add_argument("--capability", default=None, help="Filter by capability (tool_calling, vision, coding, ...)")
    sp.add_argument("--status", default=None, help="Filter by status (available, degraded, unavailable)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentinel-cli models", description="Model ecosystem management")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="List registered models")
    _add_common_filters(p)

    p = sub.add_parser("get", help="Show a single model")
    p.add_argument("model_id")

    p = sub.add_parser("register", help="Register a new model")
    p.add_argument("model_id")
    p.add_argument("--provider", required=True)
    p.add_argument("--context-window", type=int, default=4096)
    p.add_argument("--tool-calling", action="store_true")
    p.add_argument("--vision", action="store_true")
    p.add_argument("--coding", action="store_true")
    p.add_argument("--reasoning", action="store_true")
    p.add_argument("--embeddings", action="store_true")
    p.add_argument("--speed", default="unknown")
    p.add_argument("--cost", type=float, default=0.0)
    p.add_argument("--local", action="store_true")
    p.add_argument("--description", default="")
    p.add_argument("--tags", nargs="*", default=[])

    p = sub.add_parser("unregister", help="Unregister a model")
    p.add_argument("model_id")

    p = sub.add_parser("recommend", help="Recommend a model for a task")
    p.add_argument("task")

    p = sub.add_parser("strategy", help="Decide the execution strategy for a task")
    p.add_argument("task")

    p = sub.add_parser("rankings", help="Show model rankings")
    p.add_argument("--task-type", default=None)
    p.add_argument("--top-k", type=int, default=5)

    sub.add_parser("discover", help="Trigger model discovery")

    sub.add_parser("health", help="Health-check registered models")

    sub.add_parser("learning-memory", help="Show persistent learning memory status")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "list": cmd_list,
        "get": cmd_get,
        "register": cmd_register,
        "unregister": cmd_unregister,
        "recommend": cmd_recommend,
        "strategy": cmd_strategy,
        "rankings": cmd_rankings,
        "discover": cmd_discover,
        "health": cmd_health,
        "learning-memory": cmd_learning_memory,
    }
    try:
        return handlers[args.command](args)
    finally:
        _close()


if __name__ == "__main__":
    sys.exit(main())
