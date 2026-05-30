#!/usr/bin/env python3
"""Embed chunks and save a searchable index."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.search.index import ChunkIndex


def load_chunks(
    path: Path,
    *,
    season: int | None = None,
    min_season: int | None = None,
    max_season: int | None = None,
    seasons: list[int] | None = None,
) -> list[dict]:
    allowed = set(seasons) if seasons else None
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            s = row.get("season")
            if season is not None and s != season:
                continue
            if min_season is not None and (s is None or s < min_season):
                continue
            if max_season is not None and (s is None or s > max_season):
                continue
            if allowed is not None and s not in allowed:
                continue
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build embedding index from chunks.jsonl")
    parser.add_argument(
        "--chunks-path",
        type=Path,
        default=ROOT / "data" / "processed" / "chunks.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "index" / "archer_s01",
    )
    parser.add_argument("--season", type=int, default=None, help="Single season filter")
    parser.add_argument("--min-season", type=int, default=None, help="Include seasons >= this")
    parser.add_argument("--max-season", type=int, default=None, help="Include seasons <= this")
    parser.add_argument(
        "--seasons",
        type=str,
        default=None,
        help="Comma-separated seasons, e.g. 1,2",
    )
    parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--quiet", action="store_true", help="Less progress output")
    args = parser.parse_args()

    season_list = None
    if args.seasons:
        season_list = [int(x.strip()) for x in args.seasons.split(",") if x.strip()]

    chunks = load_chunks(
        args.chunks_path,
        season=args.season,
        min_season=args.min_season,
        max_season=args.max_season,
        seasons=season_list,
    )
    if not chunks:
        raise SystemExit("No chunks matched the season filter.")

    verbose = not args.quiet
    by_season = Counter(c.get("season") for c in chunks)
    if verbose:
        print(f"Loaded {len(chunks)} chunks from {args.chunks_path}", flush=True)
        for season in sorted(s for s in by_season if s is not None):
            print(f"  season {season}: {by_season[season]} chunks", flush=True)
        print(f"Embedding with {args.model} (batch_size={args.batch_size}) ...", flush=True)

    t0 = time.time()
    index = ChunkIndex.build(
        chunks,
        model_name=args.model,
        batch_size=args.batch_size,
        show_progress=verbose,
    )
    if verbose:
        print(f"Embedding done in {time.time() - t0:.1f}s", flush=True)

    index.save(args.output_dir, verbose=verbose)

    seasons_present = sorted({c.get("season") for c in chunks if c.get("season") is not None})
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "seasons": seasons_present,
                "chunk_count": len(chunks),
                "embedding_dim": int(index.embeddings.shape[1]),
                "model": args.model,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
