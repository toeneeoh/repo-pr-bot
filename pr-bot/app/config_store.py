"""
config_store.py

persistent config wrapper

TODO:
- atomic writes
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException


@dataclass(frozen=True)
class ConfigStore:
    path: Path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"repos": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, cfg: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def get_repo(self, name: str) -> dict[str, Any]:
        cfg = self.load()
        repo = cfg.get("repos", {}).get(name)
        if not repo:
            raise HTTPException(status_code=404, detail=f"unknown repo: {name}")
        return repo

    def upsert_repo(self, name: str, repo_cfg: dict[str, Any]) -> None:
        cfg = self.load()
        cfg.setdefault("repos", {})
        cfg["repos"][name] = repo_cfg
        self.save(cfg)

    def delete_repo(self, name: str) -> None:
        cfg = self.load()
        if name not in cfg.get("repos", {}):
            raise HTTPException(status_code=404, detail=f"unknown repo: {name}")
        del cfg["repos"][name]
        self.save(cfg)

    def list_repos(self) -> dict[str, Any]:
        cfg = self.load()
        return cfg.get("repos", {})
