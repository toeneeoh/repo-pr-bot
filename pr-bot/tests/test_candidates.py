from __future__ import annotations

from pathlib import Path

from app.candidates import grep_candidates
from app.repo_fs import iter_files


def test_grep_candidates_finds_lua_todo(tmp_repo: Path):
    fdir = tmp_repo / "cotlua" / "src"
    fdir.mkdir(parents=True)
    (fdir / "root.lua").write_text("-- TODO: fix thing\nprint('hi')\n", encoding="utf-8")

    files = iter_files(tmp_repo, scope=[], exlude=[])
    cands = grep_candidates(files, tmp_repo)

    ids = {c.id for c in cands}
    assert "lua-todo-triage" in ids

    cand = next(c for c in cands if c.id == "lua-todo-triage")
    assert cand.evidence
    assert cand.evidence[0]["path"] == "cotlua/src/root.lua"
