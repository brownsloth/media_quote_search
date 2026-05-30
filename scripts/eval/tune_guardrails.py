#!/usr/bin/env python3
"""Grid-search guardrail settings (optional — defaults live in guardrail_config.py)."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.search.guardrail_config import GuardrailConfig
from quote_lib.search.index import ChunkIndex


def load_queries(path: Path, season: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("category") == "negative":
                continue
            if season is not None and row.get("expected_season") not in (season, None):
                continue
            if not row.get("expected_episode_id"):
                continue
            rows.append(row)
    return rows


def episode_id(season: int | None, episode: int | None) -> str | None:
    if season is None or episode is None:
        return None
    return f"archer_S{season:02d}E{episode:02d}"


def eval_config(
    index: ChunkIndex,
    queries: list[dict],
    config: GuardrailConfig,
    *,
    top_k: int = 5,
) -> dict:
    r1_ep = r5_ep = r1_cue = r5_cue = 0
    n = len(queries)

    for row in queries:
        results = index.search(
            row["query"],
            top_k=top_k,
            use_reranker=True,
            guardrail_config=config,
        )
        expected_ep = row.get("expected_episode_id")
        expected_contains = (row.get("expected_cue_contains") or "").lower()

        hit_ep = hit_cue = False
        rank_ep = rank_cue = None

        for r in results:
            got_ep = episode_id(r.season, r.episode)
            if expected_ep and got_ep == expected_ep and rank_ep is None:
                rank_ep = r.rank
                hit_ep = True
            if expected_contains and expected_contains in r.text_line.lower() and rank_cue is None:
                rank_cue = r.rank
                hit_cue = True

        if hit_ep and rank_ep == 1:
            r1_ep += 1
        if hit_ep and rank_ep is not None and rank_ep <= 5:
            r5_ep += 1
        if hit_cue and rank_cue == 1:
            r1_cue += 1
        if hit_cue and rank_cue is not None and rank_cue <= 5:
            r5_cue += 1

    return {
        "recall_at_1_episode": r1_ep / n if n else 0,
        "recall_at_5_episode": r5_ep / n if n else 0,
        "recall_at_1_cue": r1_cue / n if n else 0,
        "recall_at_5_cue": r5_cue / n if n else 0,
        "objective": (r5_cue + 0.5 * r1_cue) / n if n else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune guardrail config on eval queries.")
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=ROOT / "data" / "index" / "archer_s01_s02",
    )
    parser.add_argument(
        "--queries-path",
        type=Path,
        default=ROOT / "eval" / "queries_archer_variants.jsonl",
        help="Eval JSONL (use queries_archer_variants.jsonl after expand_queries.py)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "stats" / "guardrail_tune.json",
    )
    parser.add_argument("--season", type=int, default=None, help="Filter eval to queries for this season")
    parser.add_argument("--quick", action="store_true", help="Smaller grid for fast iteration")
    args = parser.parse_args()

    index = ChunkIndex.load(args.index_dir)
    queries = load_queries(args.queries_path, season=args.season)
    if not queries:
        raise SystemExit("No scored eval queries matched filters.")

    if args.quick:
        grid = {
            "strict_miss_penalty": [2.0, 3.0, 4.0],
            "strict_strong_boost": [0.5, 0.75],
            "strict_strong_fuzzy_threshold": [0.85, 0.90],
        }
    else:
        grid = {
            "strict_miss_penalty": [2.0, 3.0, 4.0, 5.0],
            "strict_strong_boost": [0.5, 0.75, 1.0],
            "strict_partial_boost": [0.0, 0.25, 0.5],
            "strict_strong_fuzzy_threshold": [0.85, 0.90, 0.95],
            "soft_boost": [0.25, 0.5],
            "soft_miss_penalty": [0.5, 1.0, 1.5],
        }

    keys = list(grid.keys())
    combos = list(itertools.product(*(grid[k] for k in keys)))

    best: dict | None = None
    best_config: GuardrailConfig | None = None
    rows: list[dict] = []

    print(f"Tuning on {len(queries)} queries, {len(combos)} configs ...")
    for combo in combos:
        overrides = dict(zip(keys, combo))
        config = GuardrailConfig.from_dict({**GuardrailConfig().to_dict(), **overrides})
        metrics = eval_config(index, queries, config)
        row = {**overrides, **metrics}
        rows.append(row)
        if best is None or metrics["objective"] > best["objective"]:
            best = row
            best_config = config

    assert best_config is not None and best is not None
    rows.sort(key=lambda r: r["objective"], reverse=True)

    report = {
        "queries": len(queries),
        "combos_tried": len(combos),
        "best": best,
        "best_config": best_config.to_dict(),
        "top_10": rows[:10],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    config_path = args.output.parent / "guardrail_config.json"
    config_path.write_text(json.dumps(best_config.to_dict(), indent=2), encoding="utf-8")

    print(json.dumps({"best": best, "saved_config": str(config_path)}, indent=2))


if __name__ == "__main__":
    main()
