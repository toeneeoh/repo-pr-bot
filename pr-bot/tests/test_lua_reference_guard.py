from __future__ import annotations

from pathlib import Path

from app.llm_ollama import lua_reference_paths_exist


def test_lua_dofile_reference_must_exist(tmp_repo: Path):
    (tmp_repo / "cotlua" / "src").mkdir(parents=True)
    (tmp_repo / "cotlua" / "src" / "debugutils.lua").write_text("-- ok\n", encoding="utf-8")

    diff = (
        "diff --git a/cotlua/src/root.lua b/cotlua/src/root.lua\n"
        "--- a/cotlua/src/root.lua\n"
        "+++ b/cotlua/src/root.lua\n"
        "@@ -1 +1 @@\n"
        "-dofile('debugutils.lua')\n"
        "+dofile('debug_utils.lua')\n"
    )

    ok, why = lua_reference_paths_exist(tmp_repo, diff)
    assert ok is False
    assert "does not exist" in why


def test_lua_dofile_reference_accepts_existing_path(tmp_repo: Path):
    (tmp_repo / "Utility").mkdir()
    (tmp_repo / "Utility" / "debugutils.lua").write_text("-- ok\n", encoding="utf-8")

    diff = (
        "diff --git a/cotlua/src/root.lua b/cotlua/src/root.lua\n"
        "--- a/cotlua/src/root.lua\n"
        "+++ b/cotlua/src/root.lua\n"
        "@@ -1 +1 @@\n"
        "-dofile('debugutils.lua')\n"
        "+dofile('Utility/debugutils.lua')\n"
    )

    ok, why = lua_reference_paths_exist(tmp_repo, diff)
    assert ok is True
    assert why == ""


def test_lua_require_reference_checks_module_conventions(tmp_repo: Path):
    (tmp_repo / "mods" / "foo").mkdir(parents=True)
    (tmp_repo / "mods" / "foo" / "init.lua").write_text("-- ok\n", encoding="utf-8")

    diff = (
        "diff --git a/a.lua b/a.lua\n"
        "--- a/a.lua\n"
        "+++ b/a.lua\n"
        "@@ -1 +1 @@\n"
        "-require('mods.bar')\n"
        "+require('mods.foo')\n"
    )

    ok, why = lua_reference_paths_exist(tmp_repo, diff)
    assert ok is True
    assert why == ""
