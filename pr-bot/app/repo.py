"""
repo.py

repo inspection utilities:
- count files by extension
- count lines of code (approx)
- return lightweight repo stats for ui display
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .candidates import grep_candidates
from .models import Candidate

import fnmatch

def _read_text_lines(p: Path, max_bytes: int = 512_000) -> list[str]:
    """
    read a file into lines, best-effort. clamps size to avoid feeding megabytes to the llm.
    """
    try:
        data = p.read_bytes()
    except Exception:
        return []

    if len(data) > max_bytes:
        data = data[:max_bytes]

    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return []

    return text.splitlines()


def _infer_line_span(ev: dict[str, Any], default_radius: int) -> tuple[int | None, int | None]:
    """
    infer a (start_line, end_line) span from an evidence dict.
    lines are 1-based.
    """

    # common shapes: {"line": 123}, {"start_line": 10, "end_line": 20}, {"lineno": 5}, etc.
    line = ev.get("line") or ev.get("lineno") or ev.get("line_no")
    start_line = ev.get("start_line") or ev.get("start")
    end_line = ev.get("end_line") or ev.get("end")

    if isinstance(line, int) and line > 0:
        return max(1, line - default_radius), line + default_radius

    if isinstance(start_line, int) and start_line > 0 and isinstance(end_line, int) and end_line >= start_line:
        return start_line, end_line

    if isinstance(start_line, int) and start_line > 0 and end_line is None:
        return max(1, start_line - default_radius), start_line + default_radius

    return None, None


def extract_context(
    repo_root: Path,
    evidence: list[dict[str, Any]],
    radius: int = 40,
    max_files: int = 3,
    max_total_lines: int = 320,
) -> str:
    """
    build a context blob from evidence records.

    evidence entries should include at least:
      - path: str (relative to repo_root)

    optional:
      - line: int (1-based)
      - start_line/end_line: int (1-based)

    returns a string suitable for pasting into an llm prompt.
    """
    if not evidence:
        return ""

    chunks: list[str] = []
    total_lines = 0

    # keep ordering stable; take first N files referenced
    seen_paths: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for ev in evidence:
        path = ev.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        if path in seen_paths:
            # still include later evidence spans for same file
            ordered.append(ev)
            continue
        seen_paths.add(path)
        ordered.append(ev)
        if len(seen_paths) >= max_files:
            # still allow evidence entries for already-seen paths, but stop adding new paths
            continue

    # group evidence by path
    by_path: dict[str, list[dict[str, Any]]] = {}
    for ev in ordered:
        path = ev.get("path")
        if not isinstance(path, str):
            continue
        by_path.setdefault(path, []).append(ev)

    # only keep first max_files distinct paths
    paths = list(by_path.keys())[:max_files]

    for rel_path in paths:
        abs_path = (repo_root / rel_path).resolve()

        # safety: ensure it's under repo_root
        try:
            abs_path.relative_to(repo_root.resolve())
        except Exception:
            continue

        if not abs_path.exists() or not abs_path.is_file():
            continue

        lines = _read_text_lines(abs_path)
        if not lines:
            continue

        # build spans
        spans: list[tuple[int, int]] = []
        for ev in by_path.get(rel_path, []):
            start, end = _infer_line_span(ev, default_radius=radius)
            if start is None or end is None:
                continue
            spans.append((start, end))

        if not spans:
            # fallback: just take top of file
            spans = [(1, min(len(lines), 1 + 2 * radius))]

        # merge overlapping spans
        spans.sort()
        merged: list[tuple[int, int]] = []
        for s, e in spans:
            s = max(1, s)
            e = min(len(lines), e)
            if not merged or s > merged[-1][1] + 1:
                merged.append((s, e))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))

        # emit
        header = f"\n--- file: {rel_path} ---\n"
        chunks.append(header)

        for s, e in merged:
            # clamp total output
            if total_lines >= max_total_lines:
                break

            s0 = max(1, s)
            e0 = min(len(lines), e)

            for i in range(s0, e0 + 1):
                if total_lines >= max_total_lines:
                    break
                # 1-based line numbers for readability
                chunks.append(f"{i:>6} | {lines[i - 1]}")
                total_lines += 1

        if total_lines >= max_total_lines:
            chunks.append("\n--- context truncated ---\n")
            break

    return "\n".join(chunks).strip() + ("\n" if chunks else "")


class RepoScan(BaseModel):
    repo_name: str
    repo_path: str
    files_seen: int
    loc_estimate: int
    by_ext: dict[str, int]
    candidates: list[Candidate]

    def to_primitive(self) -> dict:
        if hasattr(super(), "dict"):
            return super().dict()
        return super().model_dump()


def iter_files(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """
    return a list of files under repo_root, respecting optional scope and exclude globs.
    """
    scope = scope or []
    exclude = exclude or []

    files: list[Path] = []

    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue

        rel = p.relative_to(repo_root).as_posix()

        # scope filtering
        if scope and not any(rel.startswith(s.rstrip("/") + "/") or rel == s for s in scope):
            continue

        # exclude filtering
        if any(fnmatch.fnmatch(rel, pat) for pat in exclude):
            continue

        files.append(p)

    return files


def scan_repo(
    repo_name: str,
    repo_path: Path,
    scope: list[str],
    exclude: list[str],
) -> RepoScan:
    files = iter_files(repo_path, scope, exclude)

    by_ext: dict[str, int] = {}
    loc = 0

    for p in files:
        ext = p.suffix.lower()
        by_ext[ext] = by_ext.get(ext, 0) + 1

        try:
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                loc += sum(1 for _ in f)
        except Exception:
            pass

    candidates = grep_candidates(files, repo_path)

    return RepoScan(
        repo_name=repo_name,
        repo_path=str(repo_path),
        files_seen=len(files),
        loc_estimate=loc,
        by_ext=by_ext,
        candidates=candidates,
    )
