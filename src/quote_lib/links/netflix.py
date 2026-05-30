"""
Netflix deep links for Archer.

Netflix episode URLs use opaque numeric video IDs:
  https://www.netflix.com/watch/{VIDEO_ID}

Season/episode numbers are NOT in the URL. We resolve SxxExx → video ID via
a cached mapping (data/netflix/archer_episodes.json), built by
scripts/data/fetch_archer_netflix_ids.py (requires a logged-in Netflix cookie).

Without a mapping entry we fall back to the show title page (no timestamp seek).

Set NETFLIX_EPISODE_LINKS=1 to enable per-episode /watch/ links when a mapping file exists.
Default is show-page only (Shakti fetch is often blocked).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

# Archer (2009) on Netflix — series title ID (not per-episode).
ARCHER_NETFLIX_SHOW_ID = "70171942"

DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[3] / "data" / "netflix" / "archer_episodes.json"


@lru_cache(maxsize=1)
def _load_mapping(path: str | None = None) -> dict:
    mapping_path = Path(
        path
        or os.environ.get("NETFLIX_MAPPING_PATH")
        or os.environ.get("SERVE_NETFLIX_MAPPING")
        or DEFAULT_MAPPING_PATH
    )
    if not mapping_path.exists():
        # HF artifact layout: serving/artifacts/netflix/archer_episodes.json
        alt = Path(os.environ.get("SERVE_ARTIFACTS_DIR", "serving/artifacts")) / "netflix" / "archer_episodes.json"
        if alt.exists():
            mapping_path = alt
    if not mapping_path.exists():
        return {"show_id": ARCHER_NETFLIX_SHOW_ID, "episodes": {}}
    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    data.setdefault("show_id", ARCHER_NETFLIX_SHOW_ID)
    data.setdefault("episodes", {})
    return data


def episode_key(season: int, episode: int) -> str:
    return f"S{season:02d}E{episode:02d}"


def resolve_netflix_link(
    season: int | None,
    episode: int | None,
    *,
    mapping_path: str | None = None,
) -> dict:
    """
    Return Netflix URL metadata for a search hit.

    link_type:
      - "episode" — direct /watch/{id} when mapped
      - "show"    — /title/{show_id} fallback (user picks episode manually)
    """
    mapping = _load_mapping(mapping_path)
    show_id = str(mapping.get("show_id") or ARCHER_NETFLIX_SHOW_ID)
    episodes: dict = mapping.get("episodes") or {}
    use_episodes = os.environ.get("NETFLIX_EPISODE_LINKS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if use_episodes and season is not None and episode is not None:
        key = episode_key(season, episode)
        video_id = episodes.get(key)
        if video_id:
            return {
                "netflix_url": f"https://www.netflix.com/watch/{video_id}",
                "netflix_link_type": "episode",
                "netflix_video_id": str(video_id),
                "netflix_show_id": show_id,
            }

    return {
        "netflix_url": f"https://www.netflix.com/title/{show_id}",
        "netflix_link_type": "show",
        "netflix_video_id": None,
        "netflix_show_id": show_id,
    }
