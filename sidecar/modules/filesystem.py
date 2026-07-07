import logging
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("aivo.filesystem")
router = APIRouter()

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

@router.post("/read")
def read_file(req: FileReadRequest):
    try:
        with open(req.path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": req.path, "content": content, "size": len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/write")
def write_file(req: FileWriteRequest):
    try:
        with open(req.path, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"path": req.path, "size": len(req.content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
def list_directory(path: str = "."):
    try:
        entries = []
        for entry in os.scandir(path):
            entries.append({
                "name": entry.name,
                "path": entry.path,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else 0,
                "modified": entry.stat().st_mtime,
            })
        return {"path": os.path.abspath(path), "entries": entries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
def search_files(query: str, root: str = "C:\\"):
    results = []
    try:
        for root_dir, dirs, files in os.walk(root):
            for f in files:
                if query.lower() in f.lower():
                    results.append(os.path.join(root_dir, f))
                if len(results) >= 50:
                    return {"query": query, "results": results}
            dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("$")]
    except PermissionError:
        log.debug("Permission denied accessing directory during search")
    except OSError as e:
        log.warning("Error during file search: %s", e)
    return {"query": query, "results": results}
