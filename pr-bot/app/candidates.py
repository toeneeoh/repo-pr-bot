"""
candidates.py

heuristic scanners using fast passes to structure candidates with evidence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import Candidate
from .path_utils import safe_relpath


def grep_candidates(files: list[Path], repo_path: Path) -> list[Candidate]:
    todo_re = re.compile(r"\b(todo|fixme|hack)\b", re.IGNORECASE)
    bare_except_re = re.compile(r"^\s*except\s*:\s*(#.*)?$", re.MULTILINE)
    shell_true_re = re.compile(r"shell\s*=\s*True")
    lua_global_re = re.compile(r"^\s*[A-Za-z_]\w*\s*=\s*.*$", re.MULTILINE)

    cands: list[Candidate] = []

    evid_todo: list[dict[str, Any]] = []
    evid_lua_todo: list[dict[str, Any]] = []
    evid_except: list[dict[str, Any]] = []
    evid_shell: list[dict[str, Any]] = []
    evid_lua_globals: list[dict[str, Any]] = []

    for f in files:
        suffix = f.suffix.lower()
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if suffix == ".py":
            for m in todo_re.finditer(text):
                line = text[: m.start()].count("\n") + 1
                evid_todo.append({"path": safe_relpath(f, repo_path), "start": line, "end": line, "why": "todo/fixme/hack marker"})
                if len(evid_todo) >= 6:
                    break

            m = bare_except_re.search(text)
            if m:
                line = text[: m.start()].count("\n") + 1
                evid_except.append({"path": safe_relpath(f, repo_path), "start": line, "end": line + 2, "why": "bare except"})

            m = shell_true_re.search(text)
            if m:
                line = text[: m.start()].count("\n") + 1
                evid_shell.append({"path": safe_relpath(f, repo_path), "start": line, "end": line + 3, "why": "subprocess shell=True"})

        if suffix == ".lua":
            for m in todo_re.finditer(text):
                line = text[: m.start()].count("\n") + 1
                evid_lua_todo.append({"path": safe_relpath(f, repo_path), "start": line, "end": line, "why": "todo/fixme/hack marker (lua)"})
                if len(evid_lua_todo) >= 12:
                    break

            for m in lua_global_re.finditer(text):
                line_txt = m.group(0)
                if line_txt.lstrip().startswith("local "):
                    continue
                line = text[: m.start()].count("\n") + 1
                evid_lua_globals.append({"path": safe_relpath(f, repo_path), "start": line, "end": line, "why": "possible implicit global assignment"})
                if len(evid_lua_globals) >= 6:
                    break

    if evid_except:
        cands.append(Candidate(
            id="py-bare-except",
            title="replace bare except with explicit exception handling",
            rationale="bare except masks bugs (systemexit/keyboardinterrupt) and reduces debuggability.",
            language="python",
            risk="low",
            churn_estimate="small",
            evidence=evid_except[:6],
        ))

    if evid_shell:
        cands.append(Candidate(
            id="py-shell-true",
            title="harden subprocess usage that enables shell=True",
            rationale="shell=True increases injection risk and complicates quoting. replace with args list when feasible.",
            language="python",
            risk="medium",
            churn_estimate="small",
            evidence=evid_shell[:6],
        ))

    if evid_lua_todo:
        cands.append(Candidate(
            id="lua-todo-triage",
            title="triage lua TODO/FIXME/HACK markers into small cleanups",
            rationale="these markers often encode known debt. convert the smallest safe ones into bite-size prs.",
            language="lua",
            risk="low",
            churn_estimate="small",
            evidence=evid_lua_todo[:2],
        ))

    if evid_lua_globals:
        cands.append(Candidate(
            id="lua-implicit-globals",
            title="reduce implicit globals by adding locals where appropriate",
            rationale="implicit globals in lua cause spooky action-at-a-distance and are hard to refactor safely.",
            language="lua",
            risk="medium",
            churn_estimate="small",
            evidence=evid_lua_globals[:6],
        ))

    if evid_todo:
        cands.append(Candidate(
            id="todo-triage",
            title="triage TODO/FIXME/HACK markers into issues or small cleanups",
            rationale="these markers often encode known debt. convert the smallest safe ones into bite-size prs.",
            language="mixed",
            risk="low",
            churn_estimate="small",
            evidence=evid_todo[:6],
        ))

    return cands
