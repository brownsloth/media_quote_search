#!/usr/bin/env python3
"""Batch-download English SRTs from OpenSubtitles for catalog shows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.util.env import load_env

load_env(ROOT / ".env")

from quote_lib.ingest.opensubtitles_client import OpenSubtitlesClient, OpenSubtitlesError
from quote_lib.parse.show_catalog import iter_episodes, load_catalog

def episode_list_for_show(show, *, max_season: int | None = None) -> list[tuple[int, int]]:
    episodes = iter_episodes(show)
    if max_season is not None:
        episodes = [(s, e) for s, e in episodes if s <= max_season]
    return episodes


def main() -> None:
    parser = argparse.ArgumentParser(description="Download subtitles via OpenSubtitles API")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog/shows_v1.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data/subs")
    parser.add_argument("--show-id", action="append", help="Limit to show_id (repeatable)")
    parser.add_argument("--max-season", type=int, default=None, help="Only first N seasons per show")
    parser.add_argument("--max-episodes", type=int, default=None, help="Cap total downloads (for smoke test)")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--manifest", type=Path, default=None, help="Write download manifest JSONL")
    args = parser.parse_args()

    env_file = ROOT / ".env"
    if not os.environ.get("OPENSUBTITLES_API_KEY"):
        hint = "Missing OPENSUBTITLES_API_KEY."
        if env_file.is_file():
            hint += f" Check values in {env_file} (no quotes needed unless value has spaces)."
        else:
            hint += f" Copy .env.example → {env_file} and fill in creds."
        raise SystemExit(hint)

    shows = load_catalog(args.catalog)
    if args.show_id:
        wanted = set(args.show_id)
        shows = [s for s in shows if s.show_id in wanted]

    client = OpenSubtitlesClient()
    client.login()

    manifest_path = args.manifest or (args.out_dir / "download_manifest.jsonl")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    downloaded = skipped = missing = failed = 0
    budget = args.max_episodes

    with manifest_path.open("a", encoding="utf-8") as mf:
        for show in shows:
            show_dir = args.out_dir / show.show_id
            show_dir.mkdir(parents=True, exist_ok=True)
            for season, episode in episode_list_for_show(show, max_season=args.max_season):
                if budget is not None and downloaded >= budget:
                    break
                dest = show_dir / f"S{season:02d}E{episode:02d}.srt"
                if args.skip_existing and dest.exists() and dest.stat().st_size > 50:
                    skipped += 1
                    continue
                try:
                    meta = client.download_episode(
                        imdb_id=show.imdb_id,
                        season=season,
                        episode=episode,
                        dest=dest,
                    )
                    if meta is None:
                        missing += 1
                        mf.write(
                            json.dumps(
                                {
                                    "show_id": show.show_id,
                                    "season": season,
                                    "episode": episode,
                                    "status": "not_found",
                                }
                            )
                            + "\n"
                        )
                    else:
                        downloaded += 1
                        mf.write(
                            json.dumps(
                                {
                                    "show_id": show.show_id,
                                    "season": season,
                                    "episode": episode,
                                    "status": "ok",
                                    "path": str(dest),
                                    **meta,
                                }
                            )
                            + "\n"
                        )
                        print(f"OK {show.show_id} S{season:02d}E{episode:02d} -> {dest.name}")
                except OpenSubtitlesError as exc:
                    failed += 1
                    mf.write(
                        json.dumps(
                            {
                                "show_id": show.show_id,
                                "season": season,
                                "episode": episode,
                                "status": "error",
                                "error": str(exc),
                            }
                        )
                        + "\n"
                    )
                    print(f"ERR {show.show_id} S{season:02d}E{episode:02d}: {exc}", file=sys.stderr)

    print(
        f"\nDone: downloaded={downloaded} skipped={skipped} missing={missing} failed={failed}\n"
        f"Manifest: {manifest_path}"
    )


if __name__ == "__main__":
    main()
