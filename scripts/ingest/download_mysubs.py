#!/usr/bin/env python3
"""Download English SRTs from my-subs.co for catalog shows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.ingest.mysubs_client import (
    download_episode,
    fetch_show_page,
    make_session,
    parse_show_page,
)
from quote_lib.parse.show_catalog import iter_episodes, load_catalog

# my-subs.co show list URLs (same site as Archer scrape in 29thMay/)
DEFAULT_MYSUBS_URLS = {
    "friends": "https://my-subs.co/showlistsubtitles-610-friends",
    "the_office": "https://my-subs.co/showlistsubtitles-1725-the-office-us",
    "game_of_thrones": "https://my-subs.co/showlistsubtitles-629-game-of-thrones",
    "breaking_bad": "https://my-subs.co/showlistsubtitles-2574-breaking-bad",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape subtitles from my-subs.co")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog/shows_v1.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data/subs")
    parser.add_argument("--show-id", action="append", help="Limit to show_id (repeatable)")
    parser.add_argument("--max-episodes", type=int, default=None, help="Cap downloads per show")
    parser.add_argument("--wait-sec", type=float, default=10.0, help="Countdown wait before file fetch")
    parser.add_argument("--pause-sec", type=float, default=2.0, help="Pause between episodes")
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    shows = load_catalog(args.catalog)
    if args.show_id:
        wanted = set(args.show_id)
        shows = [s for s in shows if s.show_id in wanted]

    session = make_session()
    manifest_path = args.manifest or (args.out_dir / "mysubs_manifest.jsonl")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    totals = {"ok": 0, "skipped": 0, "not_found": 0, "failed": 0}

    with manifest_path.open("a", encoding="utf-8") as mf:
        for show in shows:
            show_url = DEFAULT_MYSUBS_URLS.get(show.show_id)
            if not show_url:
                print(f"WARN no my-subs URL for {show.show_id}", file=sys.stderr)
                continue

            print(f"\n=== {show.show_title} ({show.show_id}) ===")
            print(f"Fetching episode list: {show_url}")
            show_html = fetch_show_page(session, show_url)
            all_links = parse_show_page(show_html)
            wanted = {(s, e) for s, e in iter_episodes(show)}
            links = [lnk for lnk in all_links if (lnk.season, lnk.episode) in wanted]
            print(f"Found {len(all_links)} on site, {len(links)} in catalog")

            show_dir = args.out_dir / show.show_id
            show_dir.mkdir(parents=True, exist_ok=True)
            downloaded_this_show = 0

            for link in links:
                if args.max_episodes is not None and downloaded_this_show >= args.max_episodes:
                    break

                dest = show_dir / f"S{link.season:02d}E{link.episode:02d}.srt"
                label = f"{show.show_id} S{link.season:02d}E{link.episode:02d}"

                try:
                    result = download_episode(
                        session,
                        link,
                        dest,
                        wait_sec=args.wait_sec,
                        pause_sec=args.pause_sec,
                    )
                    status = result["status"]
                    totals[status if status in totals else "failed"] += 1
                    if status == "ok":
                        downloaded_this_show += 1
                        print(f"OK {label} ({result.get('version', '?')})")
                    elif status == "skipped":
                        print(f"SKIP {label} (exists)")
                    else:
                        print(f"MISS {label}")

                    mf.write(
                        json.dumps(
                            {
                                "show_id": show.show_id,
                                "season": link.season,
                                "episode": link.episode,
                                **result,
                            }
                        )
                        + "\n"
                    )
                except Exception as exc:
                    totals["failed"] += 1
                    mf.write(
                        json.dumps(
                            {
                                "show_id": show.show_id,
                                "season": link.season,
                                "episode": link.episode,
                                "status": "error",
                                "error": str(exc),
                            }
                        )
                        + "\n"
                    )
                    print(f"ERR {label}: {exc}", file=sys.stderr)

    print(
        f"\nDone: ok={totals['ok']} skipped={totals['skipped']} "
        f"not_found={totals['not_found']} failed={totals['failed']}\n"
        f"Manifest: {manifest_path}"
    )


if __name__ == "__main__":
    main()
