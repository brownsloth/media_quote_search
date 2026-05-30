"""Load repo .env into os.environ (stdlib only; no python-dotenv required)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV = Path(__file__).resolve().parents[3] / ".env"


def load_env(path: Path | str | None = None, *, override: bool = False) -> bool:
    """
    Parse a .env file and set variables in os.environ.
    Returns True if the file existed and was read.
    """
    env_path = Path(path or DEFAULT_ENV)
    if not env_path.is_file():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
    return True
