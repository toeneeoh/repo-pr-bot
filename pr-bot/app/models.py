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

from pydantic import BaseModel, Field


class RepoSelectRequest(BaseModel):
    name: str = Field(..., description="human name for the repo, used as key")
    path: str = Field(..., description="path under REPO_ROOT, e.g. myproj or myproj/subdir")
    branch: str = Field("main")
    scope: list[str] = Field(default_factory=list, description="subpaths inside repo to focus on, empty = whole repo")


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
    repo: str
    candidates: list[Candidate]


class CandidatesRequest(BaseModel):
    repo: str


class PatchRequest(BaseModel):
    repo: str
    candidate_id: str


class PatchResponse(BaseModel):
    repo: str
    candidate_id: str
    diff: str
    notes: str


class ValidateRequest(BaseModel):
    repo: str
    diff: str | None = None


class ValidateResponse(BaseModel):
    repo: str
    ok: bool
    steps: list[dict[str, Any]]


@dataclass
class RepoInfo:
    name: str
    repo_path: "Path"  # avoid circular import in type-checkers
    branch: str
    scope: list[str]
    policy: Policy
