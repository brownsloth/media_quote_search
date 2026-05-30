from __future__ import annotations

from quote_lib.links.netflix import resolve_netflix_link
from quote_lib.search.index import SearchResult


def ms_to_timestamp(ms: int) -> str:
    s, ms = divmod(max(0, ms), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def episode_label(season: int | None, episode: int | None) -> str | None:
    if season is None or episode is None:
        return None
    return f"S{season:02d}E{episode:02d}"


def confidence_band(*, score: float, ce_score: float, fuzzy_score: float, rank: int) -> str:
    """High / Medium / Low — scores are CE logits + guardrail offsets, not probabilities."""
    if rank == 1 and (ce_score >= 2.0 or (ce_score >= 0.5 and fuzzy_score >= 0.85)):
        return "high"
    if ce_score >= -0.5 or fuzzy_score >= 0.75 or score >= 0.0:
        return "medium"
    return "low"


def result_to_dict(r: SearchResult) -> dict:
    label = episode_label(r.season, r.episode)
    netflix = resolve_netflix_link(r.season, r.episode)
    return {
        "rank": r.rank,
        "score": round(r.score, 4),
        "ce_score": round(r.ce_score, 4),
        "ann_score": round(r.ann_score, 4),
        "fuzzy_score": round(r.fuzzy_score, 4),
        "confidence": confidence_band(
            score=r.score,
            ce_score=r.ce_score,
            fuzzy_score=r.fuzzy_score,
            rank=r.rank,
        ),
        "chunk_id": r.chunk_id,
        "show_id": r.show_id,
        "show_title": r.show_title,
        "season": r.season,
        "episode": r.episode,
        "episode_label": label,
        "timestamp_start": ms_to_timestamp(r.start_ms),
        "timestamp_end": ms_to_timestamp(r.end_ms),
        "start_ms": r.start_ms,
        "end_ms": r.end_ms,
        "text_line": r.text_line,
        "context_before": r.context_before,
        "context_after": r.context_after,
        **netflix,
        "guardrail_note": r.guardrail_note,
    }
