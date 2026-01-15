"""
autopr.py

"agent loop" for local-only PR generation:
- selects a candidate (or uses caller-selected one)
- generates a patch with the llm
- applies to a safe worktree copy
- runs validation + pytest
- retries a bounded number of times with failure feedback
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException

from .candidates import grep_candidates
from .diff_utils import (
    strip_to_unified_diff,
    estimate_diff_churn,
    diff_paths_are_safe,
    diff_files_exist,
)
from .llm import ollama_generate
from .repo import iter_files, extract_context
from .test_runner import run_pytest
from .validate import validate_worktree
from .worktree import make_worktree, apply_patch


@dataclass(frozen=True)
class AttemptResult:
    attempt: int
    candidate_id: str
    ok: bool
    stage: str
    detail: str
    diff: str | None = None
    validation_ok: bool | None = None
    validation_steps: list[dict[str, Any]] | None = None
    tests_ok: bool | None = None
    tests_exit_code: int | None = None
    tests_output: str | None = None


def _pick_candidate(cands: Iterable[Any], prefer_language: str | None = None) -> Any:
    cands = list(cands)
    if not cands:
        raise HTTPException(status_code=404, detail="no candidates found")

    if prefer_language:
        for c in cands:
            if getattr(c, "language", None) == prefer_language:
                return c

    # lowest risk first
    order = {"low": 0, "medium": 1, "high": 2}
    return sorted(cands, key=lambda c: order.get(getattr(c, "risk", "high"), 99))[0]


def generate_patch_for_candidate(
    *,
    repo_path: Path,
    repo_name: str,
    scope: list[str],
    exclude: list[str],
    policy_constraints: dict[str, Any],
    candidate: Any,
    failure_feedback: str = "",
) -> tuple[str, dict[str, Any]]:
    """
    generates a diff for a single candidate and returns (diff, meta).

    expects candidate to have at least:
    - id/title/rationale/risk/evidence
    - optional: context_radius:int, extra_prompt_rules:str|None, target_file_only:bool
    """
    constraints = policy_constraints
    max_files = int(constraints.get("max_files_touched", 8))
    max_loc = int(constraints.get("max_loc_changed", 250))
    no_new_deps = bool(constraints.get("no_new_dependencies", True))
    preserve_api = bool(constraints.get("preserve_public_api", True))

    radius = int(getattr(candidate, "context_radius", 40))
    extra_rules = (getattr(candidate, "extra_prompt_rules", None) or "").strip()
    target_file_only = bool(getattr(candidate, "target_file_only", False))

    evidence = list(getattr(candidate, "evidence", []) or [])
    target_file: str | None = None
    if target_file_only and evidence:
        target_file = str(evidence[0].get("path") or "")
        evidence = [evidence[0]]

    context = extract_context(repo_path, evidence, radius=radius)
    if not context.strip():
        raise HTTPException(status_code=400, detail="no context could be extracted for candidate evidence")

    extra_rules_block = ("candidate-specific rules (HARD):\n" + extra_rules) if extra_rules else ""
    failure_block = ("previous attempt failed; adjust the patch. failure info:\n" + failure_feedback) if failure_feedback else ""

    prompt = textwrap.dedent(
        f"""
you are a repo co-maintainer. generate a SMALL pull-request patch.

rules (HARD):
- output ONLY a unified diff (git-style). no prose.
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

{extra_rules_block}

repo: {repo_name}

candidate:
- id: {candidate.id}
- title: {candidate.title}
- rationale: {candidate.rationale}
- risk: {candidate.risk}

repo evidence + surrounding context (copy/paste from here; do not paraphrase lines):
{context}

{failure_block}
"""
    ).strip() + "\n"

    raw = ollama_generate(prompt)
    diff = strip_to_unified_diff(raw)

    if "diff --git " not in diff:
        raise HTTPException(status_code=502, detail=f"model did not return a diff. raw output:\n{raw[:1200]}")
    if "index " in diff:
        raise HTTPException(status_code=400, detail="diff rejected: contains 'index' line (model must omit index lines)")
    if not diff_paths_are_safe(diff):
        raise HTTPException(status_code=400, detail="diff contains unsafe paths (absolute or traversal)")

    ok, msg = diff_files_exist(repo_path, diff)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    files_touched, added, removed = estimate_diff_churn(diff)
    if files_touched > max_files:
        raise HTTPException(status_code=400, detail=f"diff touches too many files: {files_touched} > {max_files}")
    if (added + removed) > max_loc:
        raise HTTPException(status_code=400, detail=f"diff too large: added+removed={added+removed} > {max_loc}")

    meta = {
        "target_file": target_file,
        "files_touched": files_touched,
        "added": added,
        "removed": removed,
    }
    return diff, meta


def autopr_run(
    *,
    repo_name: str,
    repo_path: Path,
    scope: list[str],
    exclude: list[str],
    policy_constraints: dict[str, Any],
    candidate_id: str | None,
    max_attempts: int,
    run_tests_flag: bool,
    test_expr: str | None,
    test_timeout_s: int,
) -> dict[str, Any]:
    files = iter_files(repo_path, scope, exclude)
    cands = grep_candidates(files, repo_path)

    if candidate_id:
        chosen = next((c for c in cands if c.id == candidate_id), None)
        if not chosen:
            raise HTTPException(status_code=404, detail=f"candidate_id not found in current scan: {candidate_id}")
    else:
        chosen = _pick_candidate(cands)

    attempts: list[AttemptResult] = []
    failure_feedback = ""

    max_attempts = max(1, int(max_attempts))

    for attempt in range(1, max_attempts + 1):
        # generate
        try:
            diff, _meta = generate_patch_for_candidate(
                repo_path=repo_path,
                repo_name=repo_name,
                scope=scope,
                exclude=exclude,
                policy_constraints=policy_constraints,
                candidate=chosen,
                failure_feedback=failure_feedback,
            )
        except HTTPException as e:
            attempts.append(
                AttemptResult(
                    attempt=attempt,
                    candidate_id=chosen.id,
                    ok=False,
                    stage="generate",
                    detail=str(e.detail),
                )
            )
            failure_feedback = f"generation rejected: {e.detail}"
            continue

        # apply
        work = make_worktree(repo_path)
        try:
            apply_patch(work, diff)
        except Exception as e:
            attempts.append(
                AttemptResult(
                    attempt=attempt,
                    candidate_id=chosen.id,
                    ok=False,
                    stage="apply",
                    detail=str(e),
                    diff=diff,
                )
            )
            failure_feedback = f"git apply failed: {e}"
            continue

        # validate
        validation_ok, validation_steps = validate_worktree(work)

        # tests (currently bot tests, not repo tests)
        tests_ok = None
        tests_exit = None
        tests_out = None
        if run_tests_flag:
            project_root = Path(__file__).resolve().parents[1]  # /app
            res = run_pytest(project_root=project_root, expr=test_expr, timeout_s=test_timeout_s)
            tests_ok = res.ok
            tests_exit = res.exit_code
            tests_out = res.output

        ok = bool(validation_ok) and (bool(tests_ok) if run_tests_flag else True)

        attempts.append(
            AttemptResult(
                attempt=attempt,
                candidate_id=chosen.id,
                ok=ok,
                stage="done" if ok else "validate_or_test",
                detail="ok" if ok else "validation/tests failed",
                diff=diff,
                validation_ok=validation_ok,
                validation_steps=validation_steps,
                tests_ok=tests_ok,
                tests_exit_code=tests_exit,
                tests_output=tests_out,
            )
        )

        if ok:
            return {
                "ok": True,
                "repo": repo_name,
                "candidate_id": chosen.id,
                "attempts": [a.__dict__ for a in attempts],
            }

        # retry feedback
        fb: list[str] = []
        if not validation_ok:
            fb.append("validation failed:\n" + json.dumps(validation_steps, indent=2)[:4000])
        if run_tests_flag and tests_ok is False:
            fb.append("pytest failed:\n" + (tests_out or "")[:4000])
        failure_feedback = "\n\n".join(fb) or "unknown failure"

    return {
        "ok": False,
        "repo": repo_name,
        "candidate_id": chosen.id,
        "attempts": [a.__dict__ for a in attempts],
    }
