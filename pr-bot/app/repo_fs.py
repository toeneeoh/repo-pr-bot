"""
repo_fs.py

filesystem-level utilities: safe path handling, file iteration, and evidence context extraction.
ensures repo access stays inside repo_root and provides consistent snippets to the llm.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from .path_utils import safe_relpath

from fastapi import HTTPException

import fnmatch


def iter_files(repo_path: Path, scope: list[str], exclude: list[str]) -> list[Path]:
    roots = [repo_path / s for s in scope] if scope else [repo_path]
    out: list[Path] = []

    def excluded(rel: str) -> bool:
        # exclude patterns match unix-style paths
        for pat in exclude:
            if fnmatch.fnmatch(rel, pat):
                return True
        return False

    for r in roots:
        if not r.exists():
            continue

        for p in r.rglob("*"):
            if not p.is_file():
                continue
            if ".git" in p.parts:
                continue

            rel = safe_relpath(p, repo_path)
            if excluded(rel):
                continue

            out.append(p)

    return out


def extract_context(repo_path: Path, evidence: list[dict], radius: int = 60) -> str:
    blocks: list[str] = []

    for ev in evidence:
        rel = ev.get("path")
        if not isinstance(rel, str):
            continue

        p = (repo_path / rel).resolve()
        safe_relpath(p, repo_path)  # enforce containment

        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue

        start = int(ev.get("start", 1))
        end = int(ev.get("end", start))

        start_i = max(1, start - radius)
        end_i = min(len(lines), end + radius)

        snippet = "\n".join(f"{i:>6}: {lines[i-1]}" for i in range(start_i, end_i + 1))
        why = ev.get("why", "")
        blocks.append(
            f"file: {rel}\n"
            f"evidence: lines {start}-{end} ({why})\n"
            f"{snippet}\n"
        )

    return "\n\n".join(blocks)
