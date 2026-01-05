"""
llm.py

talks to ollama.
keeps http and model-specific behavior out of routes/services.

this module should not import fastapi; raise RuntimeError on failures.
"""

from __future__ import annotations

from typing import Any

import httpx

from .settings import OLLAMA_BASE_URL, OLLAMA_MODEL


def ollama_generate(prompt: str, *, system: str = "", json_mode: bool = False) -> str:
    """call ollama /api/generate and return the response text.

    args:
        prompt: user prompt
        system: optional system prompt (ollama supports "system" in generate requests)
        json_mode: if True, ask for JSON-formatted output when supported (best-effort)

    raises:
        RuntimeError on transport/api issues or empty responses.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 800,
        },
    }
    if system:
        payload["system"] = system
    if json_mode:
        # ollama generate supports "format": "json" for some models; if unsupported,
        # ollama will ignore or error depending on version. treat errors as RuntimeError.
        payload["format"] = "json"

    timeout = httpx.Timeout(600.0, connect=10.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload)
    except Exception as e:
        raise RuntimeError(f"ollama request failed: {e!s}") from e

    if r.status_code != 200:
        raise RuntimeError(f"ollama error {r.status_code}: {r.text[:500]}")

    try:
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"ollama returned non-json response: {e!s}") from e

    resp = data.get("response")
    if not isinstance(resp, str) or not resp.strip():
        raise RuntimeError("ollama returned empty response")

    return resp
