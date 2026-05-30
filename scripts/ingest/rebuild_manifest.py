#!/usr/bin/env python3
"""Rebuild manifest/episodes.csv from processed cues + chunks JSONL."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.parse.audit import detect_file_status
from quote_lib.parse.translate_overrides import KNOWN_NON_ENGLISH


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild episodes.csv manifest.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "processed")
    args = parser.parse_args()

    cues_path = args.data_dir / "cues.jsonl"
    chunks_path = args.data_dir / "chunks.jsonl"
    out = args.data_dir / "manifest" / "episodes.csv"

    chunk_counts: dict[tuple, int] = defaultdict(int)
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r.get("show_id"), r.get("season"), r.get("episode"))
            chunk_counts[key] += 1

    by_ep: dict[tuple, dict] = {}
    with cues_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r["show_id"], r["season"], r["episode"])
            ep = by_ep.get(key)
            if ep is None:
                src = Path(r["source_path"])
                ep = {
                    "show_id": r["show_id"],
                    "season": r["season"],
                    "episode": r["episode"],
                    "episode_id": f"{r['show_id']}_S{r['season']:02d}E{r['episode']:02d}",
                    "release_group": r.get("release_group"),
                    "subtitle_path": str(src),
                    "audit_status": detect_file_status(src),
                    "cue_count": 0,
                    "dialogue_cue_count": 0,
                    "detected_language": r.get("detected_language") or "",
                    "was_translated": str(bool(r.get("was_translated"))),
                }
                by_ep[key] = ep
            ep["cue_count"] += 1
            if not r.get("is_watermark") and r.get("text_clean"):
                ep["dialogue_cue_count"] += 1

    rows: list[dict] = []
    for key, ep in sorted(by_ep.items(), key=lambda kv: (kv[0][1] or 0, kv[0][2] or 0)):
        ep["chunk_count"] = chunk_counts.get(key, 0)
        ep["verified"] = ep["audit_status"] == "valid_srt"
        s, e = ep["season"], ep["episode"]
        if (s, e) in KNOWN_NON_ENGLISH:
            ep["detected_language"] = KNOWN_NON_ENGLISH[(s, e)]
            ep["was_translated"] = "True"
        rows.append(ep)

    fieldnames = [
        "show_id",
        "season",
        "episode",
        "episode_id",
        "release_group",
        "subtitle_path",
        "audit_status",
        "detected_language",
        "was_translated",
        "cue_count",
        "dialogue_cue_count",
        "chunk_count",
        "verified",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(out)
    print(f"Wrote {len(rows)} episodes -> {out}")


if __name__ == "__main__":
    main()
