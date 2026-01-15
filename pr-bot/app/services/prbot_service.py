from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..repo import RepoScan, iter_files, scan_repo, extract_context
from ..autopr import autopr_run
from ..candidates import grep_candidates
from ..diff_utils import diff_paths_are_safe, estimate_diff_churn, strip_to_unified_diff
from ..models import (
    AutoPRRequest,
    AutoPRResponse,
    CandidatesResponse,
    PatchResponse,
    RepoInfo,
    TestRunRequest,
    TestRunResponse,
    ValidateResponse,
)
from ..test_runner import run_pytest
from ..validate import validate_worktree
from ..worktree import apply_patch, make_worktree


@dataclass
class PRBotService:
    """
    orchestrates repo scanning, patch generation, and validation.
    endpoints should call this and do nothing else.
    """

    def scan(self, info: RepoInfo) -> RepoScan:
        return scan_repo(info.name, info.repo_path, info.scope, info.exclude)

    def candidates(self, info: RepoInfo) -> CandidatesResponse:
        files = iter_files(info.repo_path, info.scope, info.exclude)
        cands = grep_candidates(files, info.repo_path)
        return CandidatesResponse(repo_name=info.name, candidates=cands)

    def candidate_patch(self, info: RepoInfo, candidate_id: str) -> PatchResponse:
        files = iter_files(info.repo_path, info.scope, info.exclude)
        cands = grep_candidates(files, info.repo_path)
        cand = next((c for c in cands if c.id == candidate_id), None)
        if cand is None:
            raise HTTPException(status_code=404, detail=f"unknown candidate_id for current repo scan: {candidate_id}")

        constraints = info.policy.constraints
        max_files = int(constraints.get("max_files_touched", 8))
        max_loc = int(constraints.get("max_loc_changed", 250))
        no_new_deps = bool(constraints.get("no_new_dependencies", True))
        preserve_api = bool(constraints.get("preserve_public_api", True))

        evidence = cand.evidence
        target_file = evidence[0].get("path") if evidence else None
        context = extract_context(info.repo_path, evidence, radius=40)

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
            - {"do not add new dependencies" if no_new_deps else "new deps allowed"}
            - {"preserve public api unless absolutely required" if preserve_api else "api changes allowed"}
            - keep changes narrowly scoped to the candidate goal
            - if the safe fix is unclear, output an EMPTY diff (no changes) rather than guessing

            candidate:
            - id: {cand.id}
            - title: {cand.title}
            - rationale: {cand.rationale}
            - risk: {cand.risk}

            repo evidence + surrounding context (copy/paste from here; do not paraphrase lines):
            {context}
            """
        ).strip() + "\n"

        from ..llm import ollama_generate # local import to avoid cycles

        raw = ollama_generate(prompt, system="", json_mode=False)
        diff = strip_to_unified_diff(raw)

        if diff and not diff_paths_are_safe(diff):
            raise HTTPException(status_code=400, detail="unsafe paths in diff output")

        files_touched, added, removed = estimate_diff_churn(diff)

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

        return PatchResponse(
            repo_name=info.name,
            candidate_id=candidate_id,
            diff=diff,
            notes=json.dumps(notes, indent=2),
        )

    def validate_diff(self, info: RepoInfo, diff: str | None) -> ValidateResponse:
        if diff is None:
            return ValidateResponse(ok=True, notes="no diff supplied")

        diff = strip_to_unified_diff(diff)

        if diff and not diff_paths_are_safe(diff):
            return ValidateResponse(ok=False, notes="unsafe paths in diff output")

        work = make_worktree(info.repo_path)
        apply_patch(work, diff)

        ok, steps = validate_worktree(work)
        return ValidateResponse(ok=ok, notes=json.dumps({"steps": steps}, indent=2))

    def run_self_tests(self, req: TestRunRequest) -> TestRunResponse:
        """run pytest for this service (the pr-bot codebase), not the target repo."""
        project_root = Path(__file__).resolve().parents[2]  # .../app
        result = run_pytest(project_root=project_root, expr=req.expr, timeout_s=req.timeout_s)
        return TestRunResponse(ok=result.ok, exit_code=result.exit_code, output=result.output)

    def autopr(self, info: RepoInfo, req: AutoPRRequest) -> AutoPRResponse:
        result = autopr_run(
            repo_name=info.name,
            repo_path=info.repo_path,
            scope=info.scope,
            exclude=info.exclude,
            policy_constraints=info.policy.constraints,
            candidate_id=req.candidate_id,
            max_attempts=req.max_attempts,
            run_tests_flag=req.run_tests,
            test_expr=req.test_expr,
            test_timeout_s=req.test_timeout_s,
        )
        return AutoPRResponse(**result)
