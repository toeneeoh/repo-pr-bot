"""
worktree.py

creates an isolated worktree and applies diffs safely via git apply.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import HTTPException

from .settings import WORK_ROOT
from .utils_run import run_cmd


def make_worktree(repo_path: Path) -> Path:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(dir=str(WORK_ROOT), prefix="worktree-"))
    shutil.copytree(repo_path, tmpdir / "repo", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    return tmpdir / "repo"


def apply_patch(work: Path, diff: str) -> None:
    patch_file = work / "_patch.diff"
    patch_file.write_text(diff, encoding="utf-8")

    rc, out = run_cmd(["git", "apply", "--check", str(patch_file)], cwd=work, timeout_s=60)
    if rc != 0:
        raise HTTPException(status_code=400, detail=f"diff failed git apply --check:\n{out[:2000]}")

    rc, out = run_cmd(["git", "apply", str(patch_file)], cwd=work, timeout_s=60)
    if rc != 0:
        raise HTTPException(status_code=400, detail=f"diff failed git apply:\n{out[:2000]}")
