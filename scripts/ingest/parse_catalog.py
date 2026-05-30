#!/usr/bin/env python3
"""Parse all catalog shows into a unified chunks.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.parse.show_catalog import catalog_summary, load_catalog
from quote_lib.parse.stats import build_chunks, write_chunks_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest multi-show SRT corpus")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog/shows_v1.json")
    parser.add_argument("--subs-dir", type=Path, default=ROOT / "data/subs")
    parser.add_argument("--out", type=Path, default=ROOT / "data/processed/universal/chunks.jsonl")
    parser.add_argument("--show-id", action="append")
    args = parser.parse_args()

    shows = load_catalog(args.catalog)
    if args.show_id:
        wanted = set(args.show_id)
        shows = [s for s in shows if s.show_id in wanted]

    all_chunks = []
    per_show: dict[str, int] = {}

    for show in shows:
        show_dir = args.subs_dir / show.show_id
        if not show_dir.is_dir():
            print(f"WARN missing subs dir: {show_dir}", file=sys.stderr)
            continue
        srts = sorted(show_dir.glob("*.srt"))
        if not srts:
            print(f"WARN no SRTs in {show_dir}", file=sys.stderr)
            continue
        chunks = build_chunks(
            srts,
            show_id=show.show_id,
            show_title=show.show_title,
        )
        per_show[show.show_id] = len(chunks)
        all_chunks.extend(chunks)
        print(f"{show.show_id}: {len(srts)} files -> {len(chunks)} chunks")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_chunks_jsonl(all_chunks, args.out)

    summary = {
        **catalog_summary(shows),
        "chunks_total": len(all_chunks),
        "chunks_per_show": per_show,
        "output": str(args.out),
    }
    summary_path = args.out.parent / "ingest_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.out} ({len(all_chunks)} chunks)")


if __name__ == "__main__":
    main()
