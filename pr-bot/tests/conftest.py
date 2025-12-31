from __future__ import annotations

from pathlib import Path
import pytest


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """
    creates a fake repo directory with a minimal structure.
    tests should write files into this directory.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo
