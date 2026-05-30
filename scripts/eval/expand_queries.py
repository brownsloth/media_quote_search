#!/usr/bin/env python3
"""
Expand the canonical eval set with human memory-style query variants.

Outputs eval/queries_archer_variants.jsonl containing:
  - all canonical rows (variant_of = null)
  - hand-curated memory typos from eval/memory_variants.json
  - auto-generated edit-distance-1 typos (optional, capped per query)

Use the expanded file for guardrail tuning and regression eval.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Adjacent-key slips for auto typos (lowercase keys).
KEY_NEIGHBORS: dict[str, str] = {
    "a": "sqwz",
    "b": "vghn",
    "c": "xdfv",
    "d": "serfcx",
    "e": "wsdr",
    "f": "drtgvc",
    "g": "ftyhbv",
    "h": "gyujnb",
    "i": "ujko",
    "j": "huiknm",
    "k": "jiolm",
    "l": "kop",
    "m": "njk",
    "n": "bhjm",
    "o": "iklp",
    "p": "ol",
    "q": "wa",
    "r": "edft",
    "s": "awedxz",
    "t": "rfgy",
    "u": "yhji",
    "v": "cfgb",
    "w": "qase",
    "x": "zsdc",
    "y": "tghu",
    "z": "asx",
}


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def auto_typo_variants(query: str, *, max_variants: int = 6) -> list[str]:
    """Single-edit typos: delete, transpose, or neighbor-key replace."""
    if not query or query.isupper() and len(query) <= 4:
        # Short shout queries: only hand-curated variants
        return []

    out: list[str] = []
    seen = {normalize_key(query)}

    def add(v: str) -> None:
        key = normalize_key(v)
        if not v or key in seen or len(v) < 3:
            return
        seen.add(key)
        out.append(v)

    for i in range(len(query)):
        # deletion
        add(query[:i] + query[i + 1 :])
        # transpose
        if i + 1 < len(query):
            add(query[:i] + query[i + 1] + query[i] + query[i + 2 :])
        ch = query[i]
        for rep in KEY_NEIGHBORS.get(ch.lower(), ""):
            repl = rep.upper() if ch.isupper() else rep
            add(query[:i] + repl + query[i + 1 :])

        if len(out) >= max_variants:
            break

    return out[:max_variants]


def expand_row(base: dict, *, query: str, variant_type: str, suffix: str) -> dict:
    row = dict(base)
    row["query_id"] = f"{base['query_id']}_{suffix}"
    row["query"] = query
    row["variant_of"] = base["query_id"]
    row["variant_type"] = variant_type
    row["category"] = "variant"
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand eval queries with memory-style variants.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "eval" / "queries_archer.jsonl",
    )
    parser.add_argument(
        "--memory-variants",
        type=Path,
        default=ROOT / "eval" / "memory_variants.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "eval" / "queries_archer_variants.jsonl",
    )
    parser.add_argument(
        "--auto-typos",
        action="store_true",
        default=True,
        help="Add auto edit-distance-1 typos (default: on)",
    )
    parser.add_argument(
        "--no-auto-typos",
        action="store_false",
        dest="auto_typos",
    )
    parser.add_argument(
        "--max-auto-per-query",
        type=int,
        default=4,
    )
    args = parser.parse_args()

    canonical = load_jsonl(args.input)
    memory = json.loads(args.memory_variants.read_text(encoding="utf-8"))

    out: list[dict] = []
    stats = {"canonical": 0, "memory": 0, "auto_typo": 0, "negative": 0}

    for base in canonical:
        row = dict(base)
        row["variant_of"] = None
        row["variant_type"] = None
        out.append(row)

        if base.get("category") == "negative":
            stats["negative"] += 1
            continue

        stats["canonical"] += 1
        seen_queries = {normalize_key(base["query"])}

        mem_list = memory.get(base["query_id"], [])
        for j, variant_query in enumerate(mem_list, start=1):
            key = normalize_key(variant_query)
            if key in seen_queries:
                continue
            seen_queries.add(key)
            out.append(
                expand_row(base, query=variant_query, variant_type="memory", suffix=f"m{j:02d}")
            )
            stats["memory"] += 1

        if args.auto_typos and base.get("category") != "negative":
            for j, variant_query in enumerate(
                auto_typo_variants(base["query"], max_variants=args.max_auto_per_query),
                start=1,
            ):
                key = normalize_key(variant_query)
                if key in seen_queries:
                    continue
                seen_queries.add(key)
                out.append(
                    expand_row(base, query=variant_query, variant_type="auto_typo", suffix=f"a{j:02d}")
                )
                stats["auto_typo"] += 1

    write_jsonl(args.output, out)

    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "total_rows": len(out),
        **stats,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
