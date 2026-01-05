"""
app/test_runner.py

run pytest inside the container in a controlled way
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_ALLOWED_EXPR = re.compile(r"^[A-Za-z0-9_\-./:*?]+$")


@dataclass(frozen=True)
class PytestResult:
    ok: bool
    exit_code: int
    output: str


def run_pytest(
    *,
    project_root: Path,
    expr: str | None = None,
    timeout_s: int = 180,
) -> PytestResult:
    """
    project_root should be the directory where `pytest` should run (contains tests/).
    expr optionally selects tests (like: "tests/test_repo_utils.py::test_x").
    """
    cmd = ["pytest", "-q"]

    if expr:
        if not _ALLOWED_EXPR.match(expr):
            return PytestResult(
                ok=False,
                exit_code=2,
                output=f"refusing to run pytest: invalid expr {expr!r}",
            )
        cmd.append(expr)

    try:
        p = subprocess.run(
            cmd,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
        )
        return PytestResult(ok=(p.returncode == 0), exit_code=p.returncode, output=p.stdout)
    except subprocess.TimeoutExpired:
        return PytestResult(ok=False, exit_code=124, output=f"pytest timed out after {timeout_s}s")
