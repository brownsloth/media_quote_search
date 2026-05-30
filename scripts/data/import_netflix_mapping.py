#!/usr/bin/env python3
"""Import archer_episodes.json from browser download into data/netflix/."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "netflix" / "archer_episodes.json"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python scripts/data/import_netflix_mapping.py /path/to/archer_episodes.json"
        )
    src = Path(sys.argv[1]).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Not found: {src}")

    data = json.loads(src.read_text(encoding="utf-8"))
    episodes = data.get("episodes") or {}
    if not episodes:
        raise SystemExit("No episodes in file — browser fetch may have failed.")

    out = Path(os.environ.get("NETFLIX_MAPPING_PATH", str(DEFAULT_OUT)))
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)

    print(f"Imported {len(episodes)} episodes → {out}")
    for key in sorted(episodes)[:5]:
        print(f"  {key} → https://www.netflix.com/watch/{episodes[key]}")
    if len(episodes) > 5:
        print(f"  ... and {len(episodes) - 5} more")
    print("\nNext: bash serving/package_artifacts.sh  (if deploying)")


if __name__ == "__main__":
    main()
