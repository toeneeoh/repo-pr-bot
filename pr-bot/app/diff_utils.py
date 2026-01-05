"""
diff_utils.py

sanitize and analyze patch diffs
"""

from __future__ import annotations

import re
from pathlib import Path


def strip_to_unified_diff(text: str) -> str:
    m = re.search(r"```diff\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip() + "\n"
    idx = text.find("diff --git")
    if idx != -1:
        return text[idx:].strip() + "\n"
    return text.strip() + "\n"


def estimate_diff_churn(diff: str) -> tuple[int, int, int]:
    files = set()
    added = 0
    removed = 0

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if m:
                files.add(m.group(2))

        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1

    return len(files), added, removed


def diff_paths_are_safe(diff: str) -> bool:
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if not m:
                return False
            for p in (m.group(1), m.group(2)):
                if p.startswith("/") or p.startswith("\\"):
                    return False
                if ".." in Path(p).parts:
                    return False
    return True
