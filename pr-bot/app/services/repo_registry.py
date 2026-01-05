from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config_store import ConfigStore
from ..models import Policy, RepoInfo
from ..settings import REPO_ROOT, CONFIG_PATH


@dataclass
class RepoRegistry:
    """
    simple registry of repos stored in CONFIG_PATH.
    repo_name is a stable key
    """

    store: ConfigStore

    @classmethod
    def default(cls) -> "RepoRegistry":
        return cls(store=ConfigStore(CONFIG_PATH))

    def list(self) -> dict[str, Any]:
        return self.store.list_repos()

    def get(self, name: str) -> RepoInfo:
        cfg = self.store.load()
        repos = cfg.get("repos", {})
        data = repos.get(name)
        if not data:
            raise HTTPException(status_code=404, detail=f"unknown repo: {name}")

        path = Path(data["path"])
        # paths are stored as absolute under REPO_ROOT in current config format.
        # tolerate relative paths by interpreting them under REPO_ROOT.
        repo_path = path if path.is_absolute() else (REPO_ROOT / path)

        return RepoInfo(
            name=name,
            repo_path=repo_path,
            branch=data.get("branch", "main"),
            scope=list(data.get("scope", [])),
            exclude=list(data.get("exclude", [])),
            policy=Policy(**data.get("policy", {})),
        )

    def upsert_from_select(self, name: str, path: str, branch: str, scope: list[str], exclude: list[str]) -> RepoInfo:
        abs_path = (REPO_ROOT / path).resolve()
        if not abs_path.exists():
            raise HTTPException(status_code=400, detail=f"repo path does not exist under REPO_ROOT: {path}")

        existing = self.store.load().get("repos", {}).get(name, {})
        policy = existing.get("policy", Policy().model_dump())

        self.store.upsert_repo(
            name=name,
            repo_cfg={
                "path": str(abs_path),
                "branch": branch,
                "scope": scope,
                "exclude": exclude,
                "policy": policy,
            },
        )
        return self.get(name)

    def set_scope(self, name: str, scope: list[str] | None = None, exclude: list[str] | None = None) -> RepoInfo:
        info = self.get(name)
        self.store.upsert_repo(
            name=name,
            repo_cfg={
                "path": str(info.repo_path),
                "branch": info.branch,
                "scope": scope if scope is not None else info.scope,
                "exclude": exclude if exclude is not None else info.exclude,
                "policy": info.policy.model_dump(),
            },
        )
        return self.get(name)

    def set_policy(self, name: str, policy: Policy) -> RepoInfo:
        info = self.get(name)
        self.store.upsert_repo(
            name=name,
            repo_cfg={
                "path": str(info.repo_path),
                "branch": info.branch,
                "scope": info.scope,
                "exclude": info.exclude,
                "policy": policy.model_dump(),
            },
        )
        return self.get(name)

    def delete(self, name: str) -> None:
        self.store.delete_repo(name)
