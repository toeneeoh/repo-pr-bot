"""
config_store.py

load/save repo registration and policy config (repos.json).

TODO:
- atomic writes
- migrate to sqlite
"""

from __future__ import annotations

import json
from typing import Any

from .settings import CONFIG_PATH


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"repos": {}}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
