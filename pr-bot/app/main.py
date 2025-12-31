"""
main.py

establishes fastapi routes
"""

from __future__ import annotations

import json
import textwrap

from pathlib import Path
from fastapi import FastAPI, HTTPException
from .models import CandidatesRequest

from .models import (
    RepoSelectRequest, Policy, CandidatesResponse,
    PatchRequest, PatchResponse,
    ValidateRequest, ValidateResponse,
    RepoInfo,
)
from .settings import REPO_ROOT
from .config_store import load_config, save_config
from .repo import iter_files, extract_context
from .candidates import grep_candidates
from .diff_utils import strip_to_unified_diff, estimate_diff_churn, diff_paths_are_safe, _diff_files_exist, _diff_touched_files
from .llm_ollama import ollama_generate, lua_reference_paths_exist
from .worktree import make_worktree, apply_patch
from .validate import validate_worktree

app = FastAPI(title="repo pr-bot", version="0.1.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # if you ever access openwebui via a different host/port, add it here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_repo_info(name: str) -> RepoInfo:
    cfg = load_config()
    repo = cfg.get("repos", {}).get(name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"unknown repo: {name}")

    repo_path = (REPO_ROOT / repo["path"]).resolve()
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail="repo path not found on disk")

    policy = Policy(**repo.get("policy", {}))
    return RepoInfo(
        name=name,
        repo_path=repo_path,
        branch=repo.get("branch", "main"),
        scope=repo.get("scope", []),
        policy=policy,
    )


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/repo/select")
def repo_select(req: RepoSelectRequest):
    cfg = load_config()
    cfg.setdefault("repos", {})
    cfg["repos"][req.name] = {
        "path": req.path,
        "branch": req.branch,
        "scope": req.scope,
        "policy": cfg["repos"].get(req.name, {}).get("policy", {}),
    }
    save_config(cfg)
    return {"ok": True, "repo": req.name}


@app.post("/repo/policy")
def repo_policy(repo: str, policy: Policy):
    cfg = load_config()
    if repo not in cfg.get("repos", {}):
        raise HTTPException(status_code=404, detail="unknown repo")
    cfg["repos"][repo]["policy"] = policy.model_dump()
    save_config(cfg)
    return {"ok": True, "repo": repo}


@app.post("/candidates", response_model=CandidatesResponse)
def candidates(req: CandidatesRequest) -> CandidatesResponse:
    info = get_repo_info(req.repo)
    files = iter_files(info.repo_path, info.scope)
    cands = grep_candidates(files, info.repo_path)
    return CandidatesResponse(repo=req.repo, candidates=cands)


@app.post("/candidate/patch", response_model=PatchResponse)
def candidate_patch(req: PatchRequest) -> PatchResponse:
    info = get_repo_info(req.repo)

    files = iter_files(info.repo_path, info.scope)
    cands = grep_candidates(files, info.repo_path)
    cand = next((c for c in cands if c.id == req.candidate_id), None)
    if cand is None:
        raise HTTPException(status_code=404, detail=f"unknown candidate_id for current repo scan: {req.candidate_id}")

    constraints = info.policy.constraints
    max_files = int(constraints.get("max_files_touched", 8))
    max_loc = int(constraints.get("max_loc_changed", 250))
    no_new_deps = bool(constraints.get("no_new_dependencies", True))
    preserve_api = bool(constraints.get("preserve_public_api", True))

    evidence = cand.evidence
    target_file: str | None = None
    radius = 40
    extra_rules = ""

    if cand.id == "lua-todo-triage" and evidence:
        target_file = str(evidence[0].get("path") or "")
        evidence = [evidence[0]]
        radius = 15
        extra_rules = """
additional rules for lua-todo-triage (ABSOLUTE, NON-NEGOTIABLE):
- you may ONLY modify the TODO/FIXME/HACK COMMENT LINE ITSELF
- the line containing the TODO marker is the ONLY line you may change
- you MUST NOT modify any executable code
- you MUST NOT modify dofile(), require(), function calls, assignments, or control flow
- you MUST NOT rename files or reference new filenames
- if clarification is not possible, output an EMPTY diff
"""

    context = extract_context(info.repo_path, evidence, radius=radius)
    if not context.strip():
        raise HTTPException(status_code=400, detail="no context could be extracted for candidate evidence")

    prompt = textwrap.dedent(
        f"""
you are a repo co-maintainer. generate a SMALL pull-request patch.

rules (HARD):
- output ONLY a unified diff (git-style). no prose.
- do NOT include any 'index ...' lines
- include at most ONE hunk
- copy surrounding context lines EXACTLY as shown
- all paths must be relative to repo root; use: diff --git a/<path> b/<path>
- do not include absolute paths and do not use .. in paths
- touch at most {max_files} files
- change at most {max_loc} total lines (added+removed, approximate)
- {("do not add new dependencies" if no_new_deps else "new deps allowed")}
- {("preserve public api unless absolutely required" if preserve_api else "api changes allowed")}
- keep changes narrowly scoped to the candidate goal
- if the safe fix is unclear, output an EMPTY diff (no changes) rather than guessing

{extra_rules}

candidate:
- id: {cand.id}
- title: {cand.title}
- rationale: {cand.rationale}
- risk: {cand.risk}

repo evidence + surrounding context (copy/paste from here; do not paraphrase lines):
{context}
"""
    )

    raw = ollama_generate(prompt)
    diff = strip_to_unified_diff(raw)

    if "diff --git " not in diff:
        raise HTTPException(status_code=502, detail=f"model did not return a diff. raw output:\n{raw[:1200]}")

    if "index " in diff:
        raise HTTPException(status_code=400, detail="diff rejected: contains 'index' line (model must omit index lines)")

    if not diff_paths_are_safe(diff):
        raise HTTPException(status_code=400, detail="diff contains unsafe paths (absolute or traversal)")

    ok, msg = _diff_files_exist(info.repo_path, diff)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)


    files_touched, added, removed = estimate_diff_churn(diff)
    if files_touched > max_files:
        raise HTTPException(status_code=400, detail=f"diff touches too many files: {files_touched} > {max_files}")
    if (added + removed) > max_loc:
        raise HTTPException(status_code=400, detail=f"diff too large: added+removed={added+removed} > {max_loc}")

    ok_refs, why = lua_reference_paths_exist(info.repo_path, diff)
    if not ok_refs:
        raise HTTPException(status_code=400, detail=f"diff rejected: {why}")

    work = make_worktree(info.repo_path)
    apply_patch(work, diff)

    ok, steps = validate_worktree(work)
    notes = {
        "files_touched": files_touched,
        "added": added,
        "removed": removed,
        "validation_ok": ok,
        "validation_steps": steps,
        "target_file": target_file,
    }

    return PatchResponse(repo=req.repo, candidate_id=req.candidate_id, diff=diff, notes=json.dumps(notes, indent=2))


@app.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest) -> ValidateResponse:
    info = get_repo_info(req.repo)
    work = make_worktree(info.repo_path)

    if req.diff:
        apply_patch(work, req.diff)

    ok, steps = validate_worktree(work)
    return ValidateResponse(repo=req.repo, ok=ok, steps=steps)
