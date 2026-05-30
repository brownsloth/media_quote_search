from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, pstdev

from quote_lib.parse.clean import whitespace_tokens
from quote_lib.parse.srt import ParsedCue, parse_srt_file


@dataclass
class DistributionStats:
    count: int
    mean: float
    stdev: float
    min: int
    p50: int
    p90: int
    p95: int
    p99: int
    max: int


@dataclass
class ChunkRecord:
    chunk_id: str
    show_id: str
    show_title: str | None
    season: int | None
    episode: int | None
    cue_index: int
    start_ms: int
    end_ms: int
    speaker: str | None
    text_line: str
    text_clean: str
    text_embed: str
    context_before: list[str]
    context_after: list[str]
    token_count_line: int
    token_count_embed: int


def summarize_ints(values: list[int]) -> DistributionStats:
    if not values:
        return DistributionStats(0, 0.0, 0.0, 0, 0, 0, 0, 0, 0)
    ordered = sorted(values)
    n = len(ordered)

    def pct(p: float) -> int:
        idx = min(n - 1, int(p * n))
        return ordered[idx]

    return DistributionStats(
        count=n,
        mean=round(mean(ordered), 2),
        stdev=round(pstdev(ordered), 2),
        min=ordered[0],
        p50=pct(0.5),
        p90=pct(0.9),
        p95=pct(0.95),
        p99=pct(0.99),
        max=ordered[-1],
    )


def build_chunks_for_episode(
    parsed_episode,
    *,
    show_id: str = "archer",
    show_title: str | None = None,
    context_window: int = 5,
) -> list[ChunkRecord]:
    dialogue = [c for c in parsed_episode.cues if not c.is_watermark and c.text_clean]
    chunks: list[ChunkRecord] = []

    for idx, cue in enumerate(dialogue):
        before = dialogue[max(0, idx - context_window) : idx]
        after = dialogue[idx + 1 : idx + 1 + context_window]
        embed_parts = [c.text_clean for c in before] + [cue.text_clean] + [c.text_clean for c in after]
        text_embed = "\n".join(embed_parts)

        season = parsed_episode.season
        episode = parsed_episode.episode
        chunk_id = f"{show_id}_S{season:02d}E{episode:02d}_{idx:05d}" if season and episode else f"{show_id}_{idx:05d}"

        chunks.append(
            ChunkRecord(
                chunk_id=chunk_id,
                show_id=show_id,
                show_title=show_title,
                season=season,
                episode=episode,
                cue_index=idx,
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                speaker=cue.speaker,
                text_line=cue.text_raw,
                text_clean=cue.text_clean,
                text_embed=text_embed,
                context_before=[c.text_raw for c in before],
                context_after=[c.text_raw for c in after],
                token_count_line=len(whitespace_tokens(cue.text_clean)),
                token_count_embed=len(whitespace_tokens(text_embed)),
            )
        )
    return chunks


def pct_truncated(token_counts: list[int], limit: int) -> float:
    if not token_counts:
        return 0.0
    truncated = sum(1 for n in token_counts if n > limit)
    return round(100.0 * truncated / len(token_counts), 2)


def top_duplicate_lines(chunks: list[ChunkRecord], top_n: int = 20) -> list[dict]:
    counter = Counter(c.text_clean for c in chunks if c.text_clean)
    rows = []
    for text, count in counter.most_common(top_n):
        if count < 2:
            break
        rows.append({"text_clean": text, "count": count})
    return rows


def build_corpus_stats(
    chunks: list[ChunkRecord],
    *,
    context_windows: list[int] | None = None,
    model_token_limits: list[int] | None = None,
) -> dict:
    context_windows = context_windows or [3, 5, 7]
    model_token_limits = model_token_limits or [256, 384]

    line_tokens = [c.token_count_line for c in chunks]
    embed_tokens_default = [c.token_count_embed for c in chunks]

    short_line_pct = round(
        100.0 * sum(1 for n in line_tokens if n < 4) / len(line_tokens), 2
    ) if line_tokens else 0.0

    context_ablation: dict[str, dict] = {}
    # Recompute embed token counts for alternate windows from stored clean lines is not
    # available here without re-parsing; caller passes extra maps if needed.
    context_ablation["default_window_in_chunks"] = {
        "window": "as stored in chunks.jsonl",
        "embed_tokens": asdict(summarize_ints(embed_tokens_default)),
    }

    truncation = {
        str(limit): {
            "pct_embed_tokens_truncated": pct_truncated(embed_tokens_default, limit)
        }
        for limit in model_token_limits
    }

    episodes = {(c.season, c.episode) for c in chunks if c.season is not None}
    speakers_detected = sum(1 for c in chunks if c.speaker)

    return {
        "summary": {
            "chunk_count": len(chunks),
            "episode_count": len(episodes),
            "speaker_attributed_cues": speakers_detected,
            "speaker_attributed_pct": round(100.0 * speakers_detected / len(chunks), 2) if chunks else 0.0,
            "short_line_lt4_tokens_pct": short_line_pct,
        },
        "cue_line_tokens": asdict(summarize_ints(line_tokens)),
        "chunk_embed_tokens": asdict(summarize_ints(embed_tokens_default)),
        "context_ablation": context_ablation,
        "model_truncation_whitespace_proxy": truncation,
        "top_duplicate_lines": top_duplicate_lines(chunks),
        "notes": [
            "Token counts use whitespace/word regex, not the embedding model tokenizer.",
            "Compare against MiniLM (256) and mpnet (384) limits as a conservative proxy.",
            "Re-run with model tokenizer once sentence-transformers is installed.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_chunks(
    srt_paths: list[Path],
    *,
    show_id: str,
    show_title: str | None = None,
    context_window: int = 5,
) -> list[ChunkRecord]:
    from quote_lib.parse.srt import parse_srt_file

    chunks: list[ChunkRecord] = []
    for path in srt_paths:
        parsed = parse_srt_file(path)
        chunks.extend(
            build_chunks_for_episode(
                parsed,
                show_id=show_id,
                show_title=show_title,
                context_window=context_window,
            )
        )
    return chunks


def write_chunks_jsonl(chunks: list[ChunkRecord], path: Path) -> None:
    write_jsonl(path, [asdict(c) for c in chunks])
