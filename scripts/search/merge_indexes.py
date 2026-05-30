#!/usr/bin/env python3
"""Merge two quote indexes (same embed model) without re-embedding."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.search.index import ChunkIndex


def load_index_dir(path: Path) -> ChunkIndex:
    return ChunkIndex.load(path)


def backfill_archer_meta(chunks: list[dict]) -> None:
    for c in chunks:
        if c.get("show_id") in (None, ""):
            c["show_id"] = "archer"
        if not c.get("show_title"):
            c["show_title"] = "Archer"


def merge_indexes(indices: list[ChunkIndex]) -> ChunkIndex:
    model = indices[0].model_name
    dim = int(indices[0].embeddings.shape[1])
    reranker = indices[0].reranker_model

    all_chunks: list[dict] = []
    all_embeddings: list[np.ndarray] = []

    for idx, index in enumerate(indices):
        if index.model_name != model:
            raise SystemExit(f"Index {idx}: model mismatch {index.model_name} != {model}")
        if int(index.embeddings.shape[1]) != dim:
            raise SystemExit(f"Index {idx}: dim mismatch")
        all_chunks.extend(index.chunks)
        all_embeddings.append(index.embeddings)

    ids = [c["chunk_id"] for c in all_chunks]
    if len(ids) != len(set(ids)):
        dupes = len(ids) - len(set(ids))
        raise SystemExit(f"Refusing to merge: {dupes} duplicate chunk_id values")

    embeddings = np.vstack(all_embeddings).astype(np.float32)
    return ChunkIndex(
        chunks=all_chunks,
        embeddings=embeddings,
        model_name=model,
        reranker_model=reranker,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge index directories (same embedding model)")
    parser.add_argument("inputs", nargs="+", type=Path, help="Index dirs to merge, in order")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/index/universal_with_archer",
    )
    parser.add_argument(
        "--backfill-archer-meta",
        action="store_true",
        default=True,
        help="Set show_id/show_title on chunks missing them (legacy archer index)",
    )
    args = parser.parse_args()

    indices = [load_index_dir(p) for p in args.inputs]
    if args.backfill_archer_meta:
        backfill_archer_meta(indices[0].chunks)

    merged = merge_indexes(indices)
    merged.save(args.output_dir)

    by_show: dict[str, int] = {}
    for c in merged.chunks:
        sid = c.get("show_id") or "unknown"
        by_show[sid] = by_show.get(sid, 0) + 1

    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "chunk_count": len(merged.chunks),
                "embedding_dim": int(merged.embeddings.shape[1]),
                "model": merged.model_name,
                "chunks_per_show": by_show,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
