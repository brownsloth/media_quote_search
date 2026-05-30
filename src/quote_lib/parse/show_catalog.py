"""Load show catalog for multi-title ingest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CATALOG = Path(__file__).resolve().parents[3] / "data" / "catalog" / "shows_v1.json"


@dataclass
class ShowSpec:
    show_id: str
    show_title: str
    media_type: str
    imdb_id: str
    seasons: int
    episodes_total: int
    season_episodes: list[int] | None = None


def load_catalog(path: Path | str | None = None) -> list[ShowSpec]:
    catalog_path = Path(path or DEFAULT_CATALOG)
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    rows: list[ShowSpec] = []
    for row in data.get("shows", []):
        rows.append(
            ShowSpec(
                show_id=row["show_id"],
                show_title=row["show_title"],
                media_type=row["media_type"],
                imdb_id=row["imdb_id"],
                seasons=row["seasons"],
                episodes_total=row["episodes_total"],
                season_episodes=row.get("season_episodes"),
            )
        )
    return rows


def iter_episodes(show: ShowSpec) -> list[tuple[int, int]]:
    if show.season_episodes:
        out: list[tuple[int, int]] = []
        for season, count in enumerate(show.season_episodes, start=1):
            for episode in range(1, count + 1):
                out.append((season, episode))
        return out
    base, rem = divmod(show.episodes_total, show.seasons)
    out = []
    for s in range(1, show.seasons + 1):
        count = base + (1 if s <= rem else 0)
        for e in range(1, count + 1):
            out.append((s, e))
    return out


def catalog_summary(shows: list[ShowSpec]) -> dict:
    return {
        "show_count": len(shows),
        "episodes_total": sum(s.episodes_total for s in shows),
        "shows": [{"show_id": s.show_id, "title": s.show_title, "episodes": s.episodes_total} for s in shows],
    }
