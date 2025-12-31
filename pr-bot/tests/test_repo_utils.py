from __future__ import annotations

from pathlib import Path
import pytest

from app.repo import extract_context
from app.path_utils import safe_relpath


def test_safe_relpath_rejects_escape(tmp_repo: Path):
    outside = tmp_repo.parent / "evil.txt"
    outside.write_text("x", encoding="utf-8")

    with pytest.raises(Exception):
        safe_relpath(outside, tmp_repo)


def test_extract_context_returns_numbered_lines(tmp_repo: Path):
    p = tmp_repo / "cotlua" / "src"
    p.mkdir(parents=True)
    f = p / "root.lua"
    f.write_text("\n".join([f"line{i}" for i in range(1, 21)]) + "\n", encoding="utf-8")

    evidence = [{"path": "cotlua/src/root.lua", "start": 10, "end": 10, "why": "todo"}]
    ctx = extract_context(tmp_repo, evidence, radius=2)

    assert "file: cotlua/src/root.lua" in ctx
    assert "evidence: lines 10-10" in ctx
    # should include line numbers
    assert "     8: line8" in ctx
    assert "    10: line10" in ctx
    assert "    12: line12" in ctx
