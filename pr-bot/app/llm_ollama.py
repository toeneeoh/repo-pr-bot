"""
llm_ollama.py

talks to ollama and provides llm-adjacent safety checks.
keeps http and model-specific behavior out of routes.
"""

from __future__ import annotations

import re

import httpx
from fastapi import HTTPException

from .settings import OLLAMA_BASE_URL, OLLAMA_MODEL


def ollama_generate(prompt: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 800,
        },
    }

    timeout = httpx.Timeout(600.0, connect=10.0)
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"ollama error {r.status_code}: {r.text[:500]}")
        data = r.json()

    resp = data.get("response")
    if not isinstance(resp, str) or not resp.strip():
        raise HTTPException(status_code=502, detail="ollama returned empty response")
    return resp


def lua_reference_paths_exist(repo_root, diff: str) -> tuple[bool, str]:
    call_re = re.compile(r"\b(dofile|require)\s*\(\s*(['\"])(.+?)\2\s*\)")
    refs: list[tuple[str, str]] = []

    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        m = call_re.search(line)
        if not m:
            continue
        refs.append((m.group(1), m.group(3)))

    for fn, target in refs:
        if fn == "dofile":
            rel = (repo_root / target).resolve()
            if rel.exists():
                continue
            base = target.split("/")[-1]
            if any(p.name == base for p in repo_root.rglob(base)):
                continue
            return False, f"lua dofile target does not exist: {target}"

        if fn == "require":
            mod_path = target.replace(".", "/")
            candidates = [f"{mod_path}.lua", f"{mod_path}/init.lua"]
            ok = any((repo_root / c).exists() for c in candidates)
            if not ok:
                base = mod_path.split("/")[-1]
                ok = any(p.stem == base for p in repo_root.rglob("*.lua"))
            if not ok:
                return False, f"lua require target likely missing: {target}"

    return True, ""
