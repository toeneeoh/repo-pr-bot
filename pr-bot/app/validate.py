"""
validate.py

runs lightweight validations on the patched worktree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils_run import run_cmd


def repo_has_suffix(work: Path, suffix: str) -> bool:
    try:
        return any(p.suffix.lower() == suffix for p in work.rglob(f"*{suffix}"))
    except Exception:
        return False


def validate_worktree(work: Path) -> tuple[bool, list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []

    if repo_has_suffix(work, ".py"):
        rc, out = run_cmd(["python", "-m", "compileall", "-q", "."], cwd=work, timeout_s=180)
        steps.append({"step": "python-compileall", "ok": rc == 0, "log": out})
    else:
        steps.append({"step": "python-compileall", "ok": True, "log": "skipped (no .py files found)"})

    if (work / "pyproject.toml").exists() or (work / "ruff.toml").exists():
        rc, out = run_cmd(["ruff", "check", "."], cwd=work, timeout_s=180)
        steps.append({"step": "ruff-check", "ok": rc == 0, "log": out})

    if (work / "tests").exists() or any(p.name.startswith("test_") for p in work.rglob("test_*.py")):
        rc, out = run_cmd(["pytest", "-q"], cwd=work, timeout_s=300)
        steps.append({"step": "pytest", "ok": rc == 0, "log": out})

    if (work / ".luacheckrc").exists():
        rc, which = run_cmd(["sh", "-lc", "command -v luacheck"], cwd=work, timeout_s=20)
        if rc == 0 and which.strip():
            rc, out = run_cmd(["luacheck", "."], cwd=work, timeout_s=180)
            steps.append({"step": "luacheck", "ok": rc == 0, "log": out})
        else:
            steps.append({"step": "luacheck", "ok": True, "log": "skipped (luacheck not installed in container)"})

    ok = all(s["ok"] for s in steps)
    return ok, steps
