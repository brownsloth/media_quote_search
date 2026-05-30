#!/usr/bin/env python3
"""Build corpus statistics from parsed chunk JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.parse.clean import whitespace_tokens
from quote_lib.parse.stats import (
    ChunkRecord,
    build_corpus_stats,
    pct_truncated,
    summarize_ints,
)


def load_chunks(path: Path) -> list[ChunkRecord]:
    rows: list[ChunkRecord] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            raw = json.loads(line)
            rows.append(ChunkRecord(**raw))
    return rows


def context_ablation_from_cues(cues_path: Path, windows: list[int]) -> dict:
    """Recompute embed token counts for alternate context windows."""
    by_episode: dict[tuple, list[str]] = {}
    with cues_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("is_watermark") or not row.get("text_clean"):
                continue
            key = (row.get("show_id"), row.get("season"), row.get("episode"))
            by_episode.setdefault(key, []).append(row["text_clean"])

    out: dict[str, dict] = {}
    for window in windows:
        token_counts: list[int] = []
        for lines in by_episode.values():
            for idx in range(len(lines)):
                before = lines[max(0, idx - window) : idx]
                after = lines[idx + 1 : idx + 1 + window]
                embed = "\n".join(before + [lines[idx]] + after)
                token_counts.append(len(whitespace_tokens(embed)))
        out[f"pm{window}"] = {
            "context_window": window,
            "embed_tokens": asdict(summarize_ints(token_counts)),
            "pct_truncated_at_256": pct_truncated(token_counts, 256),
            "pct_truncated_at_384": pct_truncated(token_counts, 384),
        }
    return out


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    line_stats = report["cue_line_tokens"]
    chunk_stats = report["chunk_embed_tokens"]
    lines = [
        "# Corpus Stats Report",
        "",
        "## Summary",
        f"- Chunks: **{summary['chunk_count']}**",
        f"- Episodes: **{summary['episode_count']}**",
        f"- Short lines (<4 tokens): **{summary['short_line_lt4_tokens_pct']}%**",
        f"- Speaker-attributed cues: **{summary['speaker_attributed_pct']}%**",
        "",
        "## Cue line tokens",
        f"- mean={line_stats['mean']} p50={line_stats['p50']} p95={line_stats['p95']} max={line_stats['max']}",
        "",
        "## Chunk embed tokens (default window)",
        f"- mean={chunk_stats['mean']} p50={chunk_stats['p50']} p95={chunk_stats['p95']} max={chunk_stats['max']}",
        "",
        "## Context window ablation",
    ]
    for key, value in report.get("context_ablation", {}).items():
        if key == "default_window_in_chunks":
            continue
        embed = value["embed_tokens"]
        lines.append(
            f"- ±{value['context_window']}: mean={embed['mean']} p95={embed['p95']} "
            f"trunc@256={value['pct_truncated_at_256']}% trunc@384={value['pct_truncated_at_384']}%"
        )
    lines.extend(["", "## Top duplicate lines"])
    for row in report.get("top_duplicate_lines", [])[:10]:
        lines.append(f"- ({row['count']}x) {row['text_clean'][:120]}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate corpus statistics report.")
    parser.add_argument(
        "--chunks-path",
        type=Path,
        default=ROOT / "data" / "processed" / "chunks.jsonl",
    )
    parser.add_argument(
        "--cues-path",
        type=Path,
        default=ROOT / "data" / "processed" / "cues.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "stats",
    )
    parser.add_argument("--context-windows", default="3,5,7")
    args = parser.parse_args()

    chunks = load_chunks(args.chunks_path)
    report = build_corpus_stats(chunks)
    windows = [int(x.strip()) for x in args.context_windows.split(",") if x.strip()]
    if args.cues_path.exists():
        report["context_ablation"] = context_ablation_from_cues(args.cues_path, windows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "corpus_stats.json"
    md_path = args.output_dir / "corpus_stats.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
