from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_FILES = (BASE_DIR / ".env", BASE_DIR / ".ENV")
_LOADED = False


def load_environment() -> None:
    global _LOADED
    if _LOADED:
        return

    for env_file in ENV_FILES:
        _load_env_file(env_file)

    _LOADED = True


def _load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        if not (os.environ.get(key) or "").strip():
            os.environ[key] = _clean_env_value(value.strip())


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
