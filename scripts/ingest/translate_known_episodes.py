#!/usr/bin/env python3
"""
Re-parse and translate only known non-English episodes, then patch cues/chunks JSONL.

Does NOT re-process the other ~135 episodes — much faster than a full re-ingest.
Episodes patched: Archer S01E04–E10 (Spanish SYS subs).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.parse.audit import detect_file_status
from quote_lib.parse.srt import parse_srt_file
from quote_lib.parse.stats import build_chunks_for_episode, write_jsonl
from quote_lib.parse.translate import TranslateOptions, translate_known_episodes
from quote_lib.parse.translate_overrides import KNOWN_NON_ENGLISH


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def episode_key(row: dict) -> tuple[int | None, int | None]:
    return (row.get("season"), row.get("episode"))


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


def find_srt(input_dir: Path, season: int, episode: int) -> Path | None:
    pattern = f"*.S{season:02d}E{episode:02d}.*.srt"
    matches = sorted(input_dir.rglob(pattern))
    return matches[0] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch translated cues/chunks for known Spanish episodes.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "29thMay" / "Archer",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data" / "processed",
    )
    parser.add_argument("--show-id", default="archer")
    parser.add_argument("--context-window", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Less progress output")
    parser.add_argument("--batch-size", type=int, default=32, help="MarianMT batch size")
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "cuda", "mps"],
        help="Torch device for MarianMT",
    )
    args = parser.parse_args()

    translate_opts = TranslateOptions(
        verbose=not args.quiet,
        batch_size=args.batch_size,
        device=args.device,
    )

    print(f"Patching {len(KNOWN_NON_ENGLISH)} known Spanish episodes ...", flush=True)

    cues_path = args.data_dir / "cues.jsonl"
    chunks_path = args.data_dir / "chunks.jsonl"
    manifest_path = args.data_dir / "manifest" / "episodes.csv"

    if not cues_path.exists() or not chunks_path.exists():
        raise SystemExit(f"Missing {cues_path} or {chunks_path} — run parse_and_store.py first.")

    patch_keys = set(KNOWN_NON_ENGLISH.keys())
    patched: list[tuple[int, int]] = []

    new_cues_by_ep: dict[tuple[int, int], list[dict]] = {}
    new_chunks_by_ep: dict[tuple[int, int], list[dict]] = {}

    for (season, episode), src_lang in sorted(KNOWN_NON_ENGLISH.items()):
        srt_path = find_srt(args.input_dir, season, episode)
        if srt_path is None:
            print(f"  SKIP S{season:02d}E{episode:02d}: no .srt found")
            continue

        status = detect_file_status(srt_path)
        if status != "valid_srt":
            print(f"  SKIP S{season:02d}E{episode:02d}: audit={status}")
            continue

        print(f"  S{season:02d}E{episode:02d} ({src_lang}->en) {srt_path.name}", flush=True)
        t0 = time.time()
        parsed = parse_srt_file(srt_path)
        dialogue_count = sum(1 for c in parsed.cues if not c.is_watermark and c.text_clean)
        print(f"    parsed {len(parsed.cues)} cues ({dialogue_count} dialogue) in {time.time() - t0:.1f}s", flush=True)

        parsed = translate_known_episodes(parsed, target_lang="en", options=translate_opts)
        if not parsed.was_translated:
            print(f"    WARNING: episode was not translated", flush=True)

        t1 = time.time()
        cue_rows = [cue_to_dict(parsed, cue, idx, args.show_id) for idx, cue in enumerate(parsed.cues)]
        chunk_rows = [asdict(c) for c in build_chunks_for_episode(
            parsed, show_id=args.show_id, context_window=args.context_window
        )]
        print(f"    built {len(chunk_rows)} chunks in {time.time() - t1:.1f}s", flush=True)
        print(f"    episode total {time.time() - t0:.1f}s", flush=True)

        key = (season, episode)
        new_cues_by_ep[key] = cue_rows
        new_chunks_by_ep[key] = chunk_rows
        patched.append(key)

    if not patched:
        raise SystemExit("No episodes patched.")

    if args.dry_run:
        print(json.dumps({"would_patch": [f"S{s:02d}E{e:02d}" for s, e in patched]}, indent=2))
        return

    print("Merging patched episodes into cues/chunks JSONL ...", flush=True)
    t_merge = time.time()
    cues = [r for r in load_jsonl(cues_path) if episode_key(r) not in patch_keys]
    chunks = [r for r in load_jsonl(chunks_path) if episode_key(r) not in patch_keys]

    for key in sorted(new_cues_by_ep.keys()):
        cues.extend(new_cues_by_ep[key])
        chunks.extend(new_chunks_by_ep[key])

    cues.sort(key=lambda r: (r.get("season") or 0, r.get("episode") or 0, r.get("cue_id", "")))
    chunks.sort(key=lambda r: (r.get("season") or 0, r.get("episode") or 0, r.get("chunk_id", "")))

    write_jsonl(cues_path, cues)
    write_jsonl(chunks_path, chunks)
    print(f"Wrote {len(cues)} cues, {len(chunks)} chunks ({time.time() - t_merge:.1f}s merge)", flush=True)

    if manifest_path.exists():
        rows: list[dict] = []
        with manifest_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            for col in ("detected_language", "was_translated"):
                if col not in fieldnames:
                    fieldnames.append(col)
            for row in reader:
                s, e = int(row["season"]), int(row["episode"])
                if (s, e) in new_cues_by_ep:
                    row["was_translated"] = "True"
                    row["detected_language"] = KNOWN_NON_ENGLISH[(s, e)]
                rows.append(row)
        tmp = manifest_path.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(manifest_path)
        print(f"Updated manifest ({manifest_path})", flush=True)

    summary = {
        "episodes_patched": [f"S{s:02d}E{e:02d}" for s, e in patched],
        "cues_total": len(cues),
        "chunks_total": len(chunks),
        "outputs": {"cues": str(cues_path), "chunks": str(chunks_path)},
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
