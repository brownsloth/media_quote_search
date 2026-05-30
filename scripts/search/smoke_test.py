#!/usr/bin/env python3
"""Smoke-test retrieval on a built index + eval queries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.search.index import ChunkIndex
from quote_lib.search.lexical import lexical_mode


def ms_to_display(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def load_queries(path: Path, *, season: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if season is not None and row.get("expected_season") not in (season, None):
                continue
            rows.append(row)
    return rows


def episode_id(season: int | None, episode: int | None) -> str | None:
    if season is None or episode is None:
        return None
    return f"archer_S{season:02d}E{episode:02d}"


def eval_query(
    index: ChunkIndex,
    row: dict,
    *,
    top_k: int = 5,
    use_reranker: bool = True,
    guardrail_config=None,
    ann_top: int = 200,
) -> dict:
    results = index.search(
        row["query"],
        top_k=top_k,
        ann_top=ann_top,
        use_reranker=use_reranker,
        guardrail_config=guardrail_config,
    )
    expected_ep = row.get("expected_episode_id")
    expected_contains = (row.get("expected_cue_contains") or "").lower()
    category = row.get("category", "unknown")

    hit_episode = False
    hit_cue = False
    rank_episode = None
    rank_cue = None

    for r in results:
        got_ep = episode_id(r.season, r.episode)
        if expected_ep and got_ep == expected_ep and rank_episode is None:
            rank_episode = r.rank
            hit_episode = True
        if expected_contains and expected_contains in r.text_line.lower() and rank_cue is None:
            rank_cue = r.rank
            hit_cue = True

    return {
        "query_id": row["query_id"],
        "query": row["query"],
        "category": category,
        "expected_episode_id": expected_ep,
        "expected_cue_contains": expected_contains or None,
        "recall_at_1_episode": hit_episode and rank_episode == 1,
        "recall_at_5_episode": hit_episode and rank_episode is not None and rank_episode <= 5,
        "recall_at_1_cue": hit_cue and rank_cue == 1,
        "recall_at_5_cue": hit_cue and rank_cue is not None and rank_cue <= 5,
        "rank_episode": rank_episode,
        "rank_cue": rank_cue,
        "top_results": [
            {
                "rank": r.rank,
                "score": round(r.score, 4),
                "episode_id": episode_id(r.season, r.episode),
                "timestamp": ms_to_display(r.start_ms),
                "line": r.text_line,
            }
            for r in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test semantic search.")
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=ROOT / "data" / "index" / "archer_s01",
    )
    parser.add_argument(
        "--queries-path",
        type=Path,
        default=ROOT / "eval" / "queries_archer.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "index" / "archer_s01" / "smoke_test_report.json",
    )
    parser.add_argument("--season", type=int, default=1, help="Eval queries for this season")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--ann-top", type=int, default=200)
    parser.add_argument("--no-reranker", action="store_true")
    parser.add_argument(
        "--guardrail-config",
        type=Path,
        default=ROOT / "data" / "processed" / "stats" / "guardrail_config.json",
    )
    parser.add_argument("--query", default=None, help="Ad-hoc single query (skip eval file)")
    args = parser.parse_args()

    index = ChunkIndex.load(args.index_dir)
    guardrail_cfg = None
    if args.guardrail_config.exists():
        from quote_lib.search.guardrail_config import GuardrailConfig

        guardrail_cfg = GuardrailConfig.from_dict(
            json.loads(args.guardrail_config.read_text(encoding="utf-8"))
        )

    search_kw = {
        "top_k": args.top_k,
        "ann_top": args.ann_top,
        "use_reranker": not args.no_reranker,
        "guardrail_config": guardrail_cfg,
    }

    if args.query:
        results = index.search(args.query, **search_kw)
        print(f"\nQuery: {args.query!r}  lexical_mode={lexical_mode(args.query)}\n")
        for r in results:
            note = f" [{r.guardrail_note}]" if r.guardrail_note else ""
            print(
                f"#{r.rank} score={r.score:.3f} (ce={r.ce_score:.3f} ann={r.ann_score:.3f} "
                f"line_fuzzy={r.fuzzy_score:.3f}) "
                f"{episode_id(r.season, r.episode)} @ {ms_to_display(r.start_ms)}{note}"
            )
            print(f"   {r.text_line}\n")
        return

    queries = load_queries(args.queries_path, season=args.season)
    report_rows = [
        eval_query(
            index,
            q,
            top_k=args.top_k,
            ann_top=args.ann_top,
            use_reranker=not args.no_reranker,
            guardrail_config=guardrail_cfg,
        )
        for q in queries
    ]

    scored = [r for r in report_rows if r["category"] != "negative"]
    negatives = [r for r in report_rows if r["category"] == "negative"]

    def rate(key: str) -> float:
        if not scored:
            return 0.0
        return round(100.0 * sum(1 for r in scored if r[key]) / len(scored), 1)

    summary = {
        "index_dir": str(args.index_dir),
        "season_filter": args.season,
        "queries_run": len(report_rows),
        "scored_queries": len(scored),
        "recall_at_1_episode_pct": rate("recall_at_1_episode"),
        "recall_at_5_episode_pct": rate("recall_at_5_episode"),
        "recall_at_1_cue_pct": rate("recall_at_1_cue"),
        "recall_at_5_cue_pct": rate("recall_at_5_cue"),
    }

    report = {"summary": summary, "results": report_rows, "negative_queries": negatives}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nWrote {args.output}")

    print("\n--- Misses (episode not in top 5) ---")
    for row in report_rows:
        if row["category"] == "negative":
            continue
        if not row["recall_at_5_episode"]:
            print(f"  {row['query_id']}: {row['query']!r} -> top: {row['top_results'][0]['line'][:70] if row['top_results'] else '?'}")


if __name__ == "__main__":
    main()
