"""Per-show streaming links (Netflix title pages, Hotstar, etc.)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from quote_lib.links.netflix import (
    ARCHER_NETFLIX_SHOW_ID,
    episode_key,
    resolve_netflix_link as resolve_archer_netflix_link,
)

DEFAULT_CATALOG = Path(__file__).resolve().parents[3] / "data" / "catalog" / "streaming_links.json"

TITLE_TO_SHOW_ID = {
    "archer": "archer",
    "friends": "friends",
    "the office": "the_office",
    "game of thrones": "game_of_thrones",
    "breaking bad": "breaking_bad",
}


@lru_cache(maxsize=1)
def _load_catalog(path: str | None = None) -> dict[str, dict]:
    catalog_path = Path(path or os.environ.get("STREAMING_LINKS_PATH", DEFAULT_CATALOG))
    if not catalog_path.is_file():
        return {}
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    return data.get("shows") or {}


def normalize_show_id(show_id: str | None, show_title: str | None = None) -> str | None:
    if show_id:
        return show_id.strip().lower()
    if show_title:
        return TITLE_TO_SHOW_ID.get(show_title.strip().lower())
    return None


def resolve_streaming_link(
    show_id: str | None,
    season: int | None,
    episode: int | None,
    *,
    show_title: str | None = None,
) -> dict:
    """
    Return streaming link metadata for a search hit.

    Fields:
      stream_url, stream_provider, stream_label, stream_link_type
    Legacy aliases: netflix_url (= stream_url for API/UI compat)
    """
    sid = normalize_show_id(show_id, show_title)
    catalog = _load_catalog()
    spec = catalog.get(sid or "")

    # Legacy Archer-only episode mapping (optional)
    if sid in (None, "archer"):
        archer = resolve_archer_netflix_link(season, episode)
        provider = "netflix"
        return {
            "stream_url": archer["netflix_url"],
            "stream_provider": provider,
            "stream_label": "Netflix",
            "stream_link_type": archer["netflix_link_type"],
            "netflix_url": archer["netflix_url"],
            "netflix_link_type": archer["netflix_link_type"],
            "netflix_video_id": archer.get("netflix_video_id"),
            "netflix_show_id": archer.get("netflix_show_id", ARCHER_NETFLIX_SHOW_ID),
        }

    if not spec:
        return {
            "stream_url": f"https://www.netflix.com/title/{ARCHER_NETFLIX_SHOW_ID}",
            "stream_provider": "netflix",
            "stream_label": "Netflix",
            "stream_link_type": "show",
            "netflix_url": f"https://www.netflix.com/title/{ARCHER_NETFLIX_SHOW_ID}",
            "netflix_link_type": "show",
            "netflix_video_id": None,
            "netflix_show_id": ARCHER_NETFLIX_SHOW_ID,
        }

    provider = spec.get("provider", "netflix")
    label = spec.get("label") or ("Hotstar" if provider == "hotstar" else "Netflix")

    if provider == "hotstar":
        url = spec["url"]
        return {
            "stream_url": url,
            "stream_provider": "hotstar",
            "stream_label": label,
            "stream_link_type": "show",
            "netflix_url": url,
            "netflix_link_type": "show",
            "netflix_video_id": None,
            "netflix_show_id": None,
        }

    title_id = str(spec.get("title_id", ""))
    url = f"https://www.netflix.com/title/{title_id}"
    ep_label = episode_key(season, episode) if season is not None and episode is not None else None

    return {
        "stream_url": url,
        "stream_provider": "netflix",
        "stream_label": label,
        "stream_link_type": "show",
        "netflix_url": url,
        "netflix_link_type": "show",
        "netflix_video_id": None,
        "netflix_show_id": title_id,
        "episode_hint": ep_label,
    }
