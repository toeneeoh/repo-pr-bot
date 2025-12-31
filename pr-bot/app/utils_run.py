"""
utils_run.py

a tiny wrapper around subprocess.run with timeout and combined stdout/stderr.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout_s: int = 120) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
        )
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return 124, f"timeout running: {' '.join(cmd)}"
