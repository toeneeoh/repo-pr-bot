"""
scan.py

repo inspection utilities:
- count files by extension
- count lines of code (approx)
- return lightweight repo stats for ui display
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repo_fs import iter_files


@dataclass(frozen=True)
class RepoScan:
    repo_name: str
    repo_path: str
    files_seen: int
    loc_estimate: int
    by_ext: dict[str, int]


def scan_repo(repo_name: str, repo_path: Path, scope: list[str], exclude: list[str]) -> RepoScan:
    files = iter_files(repo_path, scope, exclude)

    by_ext: dict[str, int] = {}
    loc = 0

    for p in files:
        ext = p.suffix.lower() or "<noext>"
        by_ext[ext] = by_ext.get(ext, 0) + 1

        # ignore huge binaries by try/except
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        loc += text.count("\n") + 1

    return RepoScan(
        repo_name=repo_name,
        repo_path=str(repo_path),
        files_seen=len(files),
        loc_estimate=loc,
        by_ext=dict(sorted(by_ext.items(), key=lambda kv: (-kv[1], kv[0]))),
    )
