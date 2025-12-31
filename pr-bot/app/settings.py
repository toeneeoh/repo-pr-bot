from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/repos"))
WORK_ROOT = Path(os.environ.get("WORK_ROOT", "/work"))
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/config/repos.json"))

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
