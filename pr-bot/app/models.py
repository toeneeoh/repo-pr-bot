"""
models.py

pydantic request/response models and small dataclasses used by the api.

TODO:
- expand candidate schema (score, tags, cost estimate, test plan).
- add question / needs_user_input structures for interactive candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from pathlib import Path

from pydantic import BaseModel, Field


class RepoSelectRequest(BaseModel):
    repo_name: str = Field(..., alias="name", description="registered repo name/key, e.g. curse-of-time")
    path: str = Field(..., description="path under REPO_ROOT, e.g. curse-of-time")
    branch: str = "main"
    scope: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=lambda: [
        "**/.git/**",
        "**/__pycache__/**",
        "**/.pytest_cache/**",
        "**/.mypy_cache/**",
        "**/.venv/**",
        "**/node_modules/**",
    ], description="glob patterns to skip")
    model_config = {"populate_by_name": True}


class Policy(BaseModel):
    goals: list[str] = Field(default_factory=lambda: ["reliability", "readability"])
    constraints: dict[str, Any] = Field(default_factory=lambda: {
        "max_files_touched": 8,
        "max_loc_changed": 250,
        "no_new_dependencies": True,
        "preserve_public_api": True,
    })
    risk_budget: Literal["low", "medium", "high"] = "low"
    require_citations: bool = True


class Candidate(BaseModel):
    id: str
    title: str
    rationale: str
    language: Literal["python", "lua", "mixed"]
    risk: Literal["low", "medium", "high"]
    churn_estimate: str
    evidence: list[dict[str, Any]]


class CandidatesResponse(BaseModel):
    repo_name: str
    candidates: list[Candidate]


class CandidatesRequest(BaseModel):
    repo_name: str


class PatchRequest(BaseModel):
    repo_name: str = Field(..., description="registered repo name, e.g. curse-of-time")
    candidate_id: str = Field(..., description="candidate identifier from /candidates, e.g. lua-todo-triage")


class PatchResponse(BaseModel):
    repo_name: str
    candidate_id: str
    diff: str
    notes: str


class ValidateRequest(BaseModel):
    repo_name: str
    diff: str | None = None


class ValidateResponse(BaseModel):
    repo_name: str
    ok: bool
    steps: list[dict[str, Any]]


@dataclass
class RepoInfo:
    name: str
    repo_path: Path
    branch: str
    scope: list[str]
    exclude: list[str]
    policy: Policy

class TestRunRequest(BaseModel):
    expr: str | None = Field(
        default=None,
        description="optional pytest selection, e.g. tests/test_repo_utils.py::test_iter_files",
    )
    timeout_s: int = Field(default=180, ge=10, le=900)


class TestRunResponse(BaseModel):
    ok: bool
    exit_code: int
    output: str

