#!/usr/bin/env python3
"""Parse, clean, and store cue + chunk JSONL artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.parse.audit import detect_file_status
from quote_lib.parse.srt import parse_srt_file
from quote_lib.parse.stats import build_chunks_for_episode, write_jsonl
from quote_lib.parse.translate import translate_known_episodes


def cue_to_dict(parsed_episode, cue, cue_idx: int, show_id: str) -> dict:
    season = parsed_episode.season
    episode = parsed_episode.episode
    cue_id = (
        f"{show_id}_S{season:02d}E{episode:02d}_{cue_idx:05d}"
        if season is not None and episode is not None
        else f"{show_id}_{cue_idx:05d}"
    )
    return {
        "cue_id": cue_id,
        "show_id": show_id,
        "season": season,
        "episode": episode,
        "release_group": parsed_episode.release_group,
        "source_path": str(parsed_episode.source_path),
        "cue_index": cue.cue_index,
        "start_ms": cue.start_ms,
        "end_ms": cue.end_ms,
        "timestamp_display": _format_ts(cue.start_ms),
        "speaker": cue.speaker,
        "text_raw": cue.text_raw,
        "text_original": cue.text_original,
        "text_clean": cue.text_clean,
        "is_watermark": cue.is_watermark,
        "detected_language": parsed_episode.detected_language,
        "was_translated": parsed_episode.was_translated,
    }


def _format_ts(ms: int) -> str:
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1_000
    millis = ms % 1_000
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse SRT files into cues/chunks JSONL.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "29thMay" / "Archer",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed",
    )
    parser.add_argument("--show-id", default="archer")
    parser.add_argument("--context-window", type=int, default=5)
    parser.add_argument(
        "--only-valid",
        action="store_true",
        help="Skip files that fail audit (html, empty, low cue count)",
    )
    parser.add_argument(
        "--translate-known",
        action="store_true",
        help="Translate known non-English episodes to English (MarianMT; no langdetect)",
    )
    parser.add_argument(
        "--translate-non-english",
        action="store_true",
        help=argparse.SUPPRESS,  # alias for --translate-known
    )
    args = parser.parse_args()

    cues_path = args.output_dir / "cues.jsonl"
    chunks_path = args.output_dir / "chunks.jsonl"
    manifest_path = args.output_dir / "manifest" / "episodes.csv"

    cue_rows: list[dict] = []
    chunk_rows: list[dict] = []
    manifest_rows: list[dict] = []

    files = sorted(args.input_dir.rglob("*.srt"))
    skipped = 0
    translated_episodes = 0

    for path in files:
        status = detect_file_status(path)
        if args.only_valid and status != "valid_srt":
            skipped += 1
            continue

        parsed = parse_srt_file(path)
        if args.translate_known or args.translate_non_english:
            before = parsed.was_translated
            parsed = translate_known_episodes(parsed, target_lang="en")
            if parsed.was_translated and not before:
                translated_episodes += 1
                print(f"  translated {path.name} ({parsed.detected_language}->en)")

        dialogue = [c for c in parsed.cues if not c.is_watermark and c.text_clean]
        chunks = build_chunks_for_episode(
            parsed,
            show_id=args.show_id,
            context_window=args.context_window,
        )

        for idx, cue in enumerate(parsed.cues):
            cue_rows.append(cue_to_dict(parsed, cue, idx, args.show_id))

        chunk_rows.extend(asdict(chunk) for chunk in chunks)

        manifest_rows.append(
            {
                "show_id": args.show_id,
                "season": parsed.season,
                "episode": parsed.episode,
                "episode_id": (
                    f"{args.show_id}_S{parsed.season:02d}E{parsed.episode:02d}"
                    if parsed.season is not None and parsed.episode is not None
                    else None
                ),
                "release_group": parsed.release_group,
                "subtitle_path": str(path),
                "audit_status": status,
                "detected_language": parsed.detected_language or "",
                "was_translated": parsed.was_translated,
                "cue_count": len(parsed.cues),
                "dialogue_cue_count": len(dialogue),
                "chunk_count": len(chunks),
                "verified": status == "valid_srt",
            }
        )

    write_jsonl(cues_path, cue_rows)
    write_jsonl(chunks_path, chunk_rows)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {
        "files_seen": len(files),
        "files_skipped": skipped,
        "episodes_in_manifest": len(manifest_rows),
        "episodes_translated": translated_episodes,
        "cues_written": len(cue_rows),
        "chunks_written": len(chunk_rows),
        "context_window": args.context_window,
        "translate_known": args.translate_known or args.translate_non_english,
        "outputs": {
            "cues": str(cues_path),
            "chunks": str(chunks_path),
            "manifest": str(manifest_path),
        },
    }
    summary_path = args.output_dir / "parse_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
