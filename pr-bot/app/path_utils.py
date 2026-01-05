"""
path_utils.py

small path helpers used across the codebase.
kept as a standalone module to avoid circular imports.
"""

from __future__ import annotations

from pathlib import Path


def safe_relpath(p: Path, root: Path) -> str:
    """
    return a normalized relative path from root to p.
    raises ValueError if p is not under root.
    """
    try:
        rel = p.resolve().relative_to(root.resolve())
    except Exception as e:
        raise ValueError("path escapes repo root") from e
    return str(rel).replace("\\", "/")
