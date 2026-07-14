import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from services.filesystem_service import FilesystemService

log = logging.getLogger("sentinel.filesystem")
router = APIRouter()

# Keep _svc for backward compatibility (other modules may reference it)
_svc = FilesystemService()

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str


def _identity_dict(request: Request) -> dict:
    identity = getattr(request.state, "identity", None)
    if identity is None:
        return {"user_id": "local", "client_id": "unknown", "level": "confirm"}
    return {
        "user_id": identity.user_id,
        "username": getattr(identity, "username", ""),
        "role": getattr(identity, "role", "user"),
        "level": identity.level,
        "is_authenticated": getattr(identity, "is_authenticated", False),
        "is_local": getattr(identity, "is_local", True),
    }


def _result_or_raise(result, status_code: int = 403):
    if not result.success:
        error = result.error or "Unknown error"
        if "blocked" in error.lower() or "denied" in error.lower() or "blocked" in error.lower():
            raise HTTPException(status_code=status_code, detail=error)
        raise HTTPException(status_code=500, detail=error)
    return result.data


@router.post("/read")
async def read_file(req: FileReadRequest, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    result = await orch.execute_direct(
        "filesystem.read", {"path": req.path},
        identity=_identity_dict(request),
    )
    return _result_or_raise(result.tool_result)


@router.post("/write")
async def write_file(req: FileWriteRequest, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    result = await orch.execute_direct(
        "filesystem.write", {"path": req.path, "content": req.content},
        identity=_identity_dict(request),
    )
    return _result_or_raise(result.tool_result)


@router.get("/list")
async def list_directory(request: Request, path: str = "."):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    result = await orch.execute_direct(
        "filesystem.list", {"path": path},
        identity=_identity_dict(request),
    )
    return _result_or_raise(result.tool_result)


@router.get("/search")
async def search_files(request: Request, query: str, root: str = "C:\\"):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    result = await orch.execute_direct(
        "filesystem.search", {"query": query, "root": root},
        identity=_identity_dict(request),
    )
    return _result_or_raise(result.tool_result)


def wire_dependencies(audit_svc=None):
    if audit_svc:
        _svc.set_audit_service(audit_svc)
