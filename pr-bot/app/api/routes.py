from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..models import (
    AutoPRRequest,
    AutoPRResponse,
    Policy,
    RepoSelectRequest,
    RepoScanResponse,
    TestRunRequest,
    TestRunResponse,
    ValidateRequest,
    ValidateResponse,
)
from ..services.prbot_service import PRBotService
from ..services.repo_registry import RepoRegistry

router = APIRouter()


class ScopeUpdateRequest(BaseModel):
    scope: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


def _registry() -> RepoRegistry:
    return RepoRegistry.default()


def _svc() -> PRBotService:
    return PRBotService()


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@router.get("/repos")
def repos_list() -> dict[str, Any]:
    return {"repos": _registry().list()}


@router.get("/repos/{name}")
def repos_get(name: str) -> dict[str, Any]:
    info = _registry().get(name)
    return {
        "name": info.name,
        "path": str(info.repo_path),
        "branch": info.branch,
        "scope": info.scope,
        "exclude": info.exclude,
        "policy": info.policy.model_dump(),
    }


@router.delete("/repos/{name}")
def repos_delete(name: str) -> dict[str, Any]:
    _registry().delete(name)
    return {"ok": True}


@router.post("/repos/register")
def repos_register(req: RepoSelectRequest) -> dict[str, Any]:
    info = _registry().upsert_from_select(
        name=req.repo_name,
        path=req.path,
        branch=req.branch,
        scope=req.scope,
        exclude=req.exclude,
    )
    return {"ok": True, "repo": info.name}


@router.post("/repos/{name}/scope")
def repos_scope(name: str, req: ScopeUpdateRequest) -> dict[str, Any]:
    info = _registry().set_scope(name, scope=req.scope, exclude=req.exclude)
    return {"ok": True, "repo": info.name, "scope": info.scope, "exclude": info.exclude}


@router.post("/repos/{name}/policy")
def repos_policy(name: str, policy: Policy) -> dict[str, Any]:
    info = _registry().set_policy(name, policy)
    return {"ok": True, "repo": info.name, "policy": info.policy.model_dump()}


@router.post("/repos/{name}/validate", response_model=ValidateResponse)
def repos_validate(name: str, req: ValidateRequest) -> ValidateResponse:
    info = _registry().get(name)
    return _svc().validate_diff(info, req.diff)


@router.post("/tests/run", response_model=TestRunResponse)
def tests_run(req: TestRunRequest) -> TestRunResponse:
    return _svc().run_self_tests(req)



@router.post("/repos/{name}/scan", response_model=RepoScanResponse)
def repos_scan(name: str) -> RepoScanResponse:
    info = _registry().get(name)
    scan = _svc().scan(info)
    return RepoScanResponse(**scan.model_dump())


@router.post("/repos/{name}/autopr", response_model=AutoPRResponse)
def repos_autopr(name: str, req: AutoPRRequest) -> AutoPRResponse:
    info = _registry().get(name)
    return _svc().autopr(info, req)
