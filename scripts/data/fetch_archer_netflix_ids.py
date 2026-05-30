#!/usr/bin/env python3
"""
Build data/netflix/archer_episodes.json — SxxExx → Netflix /watch/{VIDEO_ID}.

Uses **form-urlencoded** Shakti (not the old JSON body from oldgalileo/shakti).
Reference: CastagnaIT/plugin.video.netflix.

Requires a logged-in Netflix session (IDs are region-specific).

Usage:
  export NETFLIX_ID='...'
  export SECURE_NETFLIX_ID='...'
  bash scripts/data/run_fetch_netflix.sh

Or:
  export NETFLIX_COOKIE='NetflixId=...; SecureNetflixId=...'

Optional env:
  NETFLIX_SHOW_ID=70171942
  NETFLIX_BUILD_ID=...      skip auto-detect
  NETFLIX_AUTH_URL=...      skip auto-detect
  NETFLIX_DEBUG=1           verbose Shakti logging
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.links.netflix import ARCHER_NETFLIX_SHOW_ID
from quote_lib.links.netflix_auth import require_netflix_cookie
from quote_lib.links.shakti_client import (
    ShaktiError,
    ShaktiHTTPError,
    build_episode_fetch_paths,
    detect_session,
    path_evaluator,
    walk_show_episodes,
)

OUTPUT = Path(
    os.environ.get("NETFLIX_MAPPING_PATH", str(ROOT / "data" / "netflix" / "archer_episodes.json"))
)
SHOW_ID = int(os.environ.get("NETFLIX_SHOW_ID", ARCHER_NETFLIX_SHOW_ID))


def main() -> None:
    cookie = require_netflix_cookie()
    build_id = os.environ.get("NETFLIX_BUILD_ID")
    auth_url = os.environ.get("NETFLIX_AUTH_URL")
    if not build_id or not auth_url:
        print("Detecting BUILD_IDENTIFIER + authURL from netflix.com/browse ...")
        try:
            detected_build, detected_auth = detect_session(cookie)
        except ShaktiError as e:
            raise SystemExit(str(e)) from e
        build_id = build_id or detected_build
        auth_url = auth_url or detected_auth

    print(f"Show ID: {SHOW_ID}")
    print(f"Shakti build: {build_id}")
    print(f"authURL length: {len(auth_url)}")
    if os.environ.get("NETFLIX_DEBUG"):
        print(f"authURL prefix: {auth_url[:12]}...")

    paths = build_episode_fetch_paths(SHOW_ID, max_seasons=20, max_episodes=35)
    print(f"Requesting {len(paths)} Shakti path(s) ...")

    try:
        resp = path_evaluator(cookie=cookie, build_id=build_id, auth_url=auth_url, paths=paths)
    except ShaktiHTTPError as e:
        raise SystemExit(
            f"Shakti request failed: HTTP {e.status} {e.reason}\n{e.body[:500].decode('utf-8', errors='replace')}"
        ) from e
    except ShaktiError as e:
        raise SystemExit(f"Shakti request failed: {e}") from e
    except Exception as e:
        raise SystemExit(f"Shakti request failed: {e}") from e

    graph = resp.get("jsonGraph") or resp
    episodes = walk_show_episodes(graph, SHOW_ID)

    if not episodes:
        print("WARNING: no episodes parsed — dumping response head for debugging.", file=sys.stderr)
        print(json.dumps(resp, indent=2)[:6000], file=sys.stderr)
        raise SystemExit(1)

    show_title = "Archer"
    videos = graph.get("videos") or {}
    show_node = videos.get(str(SHOW_ID)) or {}
    title_node = show_node.get("title")
    if isinstance(title_node, dict) and title_node.get("value"):
        show_title = str(title_node["value"])

    payload = {
        "show_id": str(SHOW_ID),
        "show_title": show_title,
        "shakti_build_id": build_id,
        "episode_count": len(episodes),
        "episodes": dict(sorted(episodes.items())),
        "source": "https://github.com/oldgalileo/shakti",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {len(episodes)} episode watch IDs → {OUTPUT}")
    for key in sorted(episodes)[:5]:
        print(f"  {key} → https://www.netflix.com/watch/{episodes[key]}")
    if len(episodes) > 5:
        print(f"  ... and {len(episodes) - 5} more")


if __name__ == "__main__":
    main()
