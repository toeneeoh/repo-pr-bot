from __future__ import annotations

from app.diff_utils import strip_to_unified_diff, estimate_diff_churn, diff_paths_are_safe


def test_strip_to_unified_diff_prefers_fenced_block():
    raw = "blah\n```diff\ndiff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-a\n+b\n```\nmore"
    diff = strip_to_unified_diff(raw)
    assert diff.startswith("diff --git a/a.txt b/a.txt")


def test_strip_to_unified_diff_falls_back_to_first_diff_git():
    raw = "prose...\ndiff --git a/x b/x\n--- a/x\n+++ b/x\n"
    diff = strip_to_unified_diff(raw)
    assert diff.startswith("diff --git a/x b/x")


def test_estimate_diff_churn_counts_files_and_lines():
    diff = (
        "diff --git a/a.lua b/a.lua\n"
        "--- a/a.lua\n"
        "+++ b/a.lua\n"
        "@@ -1,2 +1,2 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/b.lua b/b.lua\n"
        "--- a/b.lua\n"
        "+++ b/b.lua\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
    )
    files, added, removed = estimate_diff_churn(diff)
    assert files == 2
    assert added == 2
    assert removed == 2


def test_diff_paths_are_safe_rejects_absolute_and_traversal():
    bad_abs = "diff --git a//etc/passwd b//etc/passwd\n--- a//etc/passwd\n+++ b//etc/passwd\n"
    assert diff_paths_are_safe(bad_abs) is False

    bad_trav = "diff --git a/../x b/../x\n--- a/../x\n+++ b/../x\n"
    assert diff_paths_are_safe(bad_trav) is False

    ok = "diff --git a/cotlua/src/root.lua b/cotlua/src/root.lua\n--- a/cotlua/src/root.lua\n+++ b/cotlua/src/root.lua\n"
    assert diff_paths_are_safe(ok) is True
