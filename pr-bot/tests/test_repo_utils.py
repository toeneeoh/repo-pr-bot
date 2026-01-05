from __future__ import annotations

from pathlib import Path

import pytest

from app.repo_fs import iter_files, extract_context


def _write(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def test_iter_files_whole_repo_ignores_git(tmp_path: Path) -> None:
    repo = tmp_path / "fake_repo"
    _write(repo / "a.lua", "-- TODO: hello\nx=1\n")
    _write(repo / "b.py", "# TODO: hi\nprint('x')\n")
    _write(repo / ".git" / "config", "nope\n")
    _write(repo / "nested" / "c.lua", "-- ok\n")

    files = iter_files(repo, scope=[], exclude=[])
    rels = {p.relative_to(repo).as_posix() for p in files}

    assert "a.lua" in rels
    assert "b.py" in rels
    assert "nested/c.lua" in rels
    assert ".git/config" not in rels


def test_iter_files_with_scope_limits_to_subpaths(tmp_path: Path) -> None:
    repo = tmp_path / "fake_repo"
    _write(repo / "root.lua", "-- root\n")
    _write(repo / "src" / "one.lua", "-- one\n")
    _write(repo / "src" / "two.lua", "-- two\n")
    _write(repo / "tests" / "t.lua", "-- t\n")

    files = iter_files(repo, scope=["src"], exclude=[])
    rels = {p.relative_to(repo).as_posix() for p in files}

    assert "src/one.lua" in rels
    assert "src/two.lua" in rels
    assert "root.lua" not in rels
    assert "tests/t.lua" not in rels


def test_extract_context_returns_snippet_with_line_numbers(tmp_path: Path) -> None:
    repo = tmp_path / "fake_repo"
    text = "\n".join(
        [
            "line1",
            "line2",
            "-- TODO: fix me",
            "line4",
            "line5",
        ]
    )
    _write(repo / "src" / "main.lua", text + "\n")

    evidence = [
        {
            "path": "src/main.lua",
            "start": 3,
            "end": 3,
            "why": "todo marker",
        }
    ]

    out = extract_context(repo, evidence, radius=1)

    # should include header + numbered lines around 3 (2..4)
    assert "file: src/main.lua" in out
    assert "evidence: lines 3-3" in out
    assert "     2: line2" in out
    assert "     3: -- TODO: fix me" in out
    assert "     4: line4" in out


def test_extract_context_skips_missing_files(tmp_path: Path) -> None:
    repo = tmp_path / "fake_repo"
    repo.mkdir(parents=True, exist_ok=True)

    evidence = [{"path": "nope.lua", "start": 1, "end": 1, "why": "missing"}]
    out = extract_context(repo, evidence, radius=1)

    assert out.strip() == ""


def test_extract_context_rejects_path_escape(tmp_path: Path) -> None:
    repo = tmp_path / "fake_repo"
    _write(repo / "ok.lua", "ok\n")

    # attempts traversal outside repo
    evidence = [{"path": "../evil.lua", "start": 1, "end": 1, "why": "escape"}]

    with pytest.raises(Exception):
        extract_context(repo, evidence, radius=1)
