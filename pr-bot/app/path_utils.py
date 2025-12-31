from pathlib import Path
from fastapi import HTTPException

def safe_relpath(p: Path, root: Path) -> str:
    try:
        rel = p.resolve().relative_to(root.resolve())
    except Exception:
        raise HTTPException(status_code=400, detail="path escapes repo root")
    return str(rel).replace("\\", "/")
