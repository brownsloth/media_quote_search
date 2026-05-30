#!/usr/bin/env python3
"""Download quote index artifacts from Hugging Face Hub."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

DEFAULT_REPO = "1starun8-research/archer-quote-index"


def download_artifacts(
    repo_id: str | None = None,
    dest: Path | str | None = None,
    token: str | None = None,
) -> Path:
    repo_id = repo_id or os.environ.get("HF_ARTIFACTS_REPO", DEFAULT_REPO)
    dest = Path(dest or os.environ.get("SERVE_ARTIFACTS_DIR", "serving/artifacts"))
    token = token or os.environ.get("HF_TOKEN")

    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {repo_id} -> {dest}")

    snapshot_download(
        repo_id=repo_id,
        repo_type="model",
        local_dir=str(dest),
        allow_patterns=["index/*", "guardrail_config.json", "netflix/*"],
        token=token,
    )

    required = [
        dest / "index" / "embeddings.npy",
        dest / "index" / "chunks.jsonl",
        dest / "index" / "meta.json",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Download finished but required files are missing:\n"
            + "\n".join(f"  - {p}" for p in missing)
        )

    netflix_map = dest / "netflix" / "archer_episodes.json"
    if netflix_map.exists():
        n = len(json.loads(netflix_map.read_text()).get("episodes", {}))
        print(f"  Netflix episode map: {n} entries")
    else:
        print("  Netflix episode map: missing (buttons fall back to show title page)")

    print("Artifacts ready:")
    for p in required:
        mb = p.stat().st_size / (1024 * 1024)
        print(f"  {p} ({mb:.1f} MB)")
    return dest


def main() -> None:
    try:
        download_artifacts()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
