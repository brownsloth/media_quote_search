#!/usr/bin/env python3
"""
Estimate local ingest + embed time from a sample of existing SRTs.

Run before full catalog ingest to decide chunking strategy and RunPod vs local embed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.parse.show_catalog import catalog_summary, load_catalog
from quote_lib.parse.stats import build_chunks


def find_sample_srts(subs_dir: Path, sample_n: int) -> list[Path]:
    srts: list[Path] = []
    if subs_dir.is_dir():
        for show_dir in sorted(subs_dir.iterdir()):
            if not show_dir.is_dir():
                continue
            srts.extend(sorted(show_dir.glob("*.srt")))
    if not srts:
        for candidate in (ROOT / "29thMay" / "Archer", ROOT / "29thMay"):
            if candidate.is_dir():
                srts = sorted(candidate.rglob("*.srt"))
                if srts:
                    break
    return srts[:sample_n]


def fmt_seconds(sec: float) -> str:
    if sec < 60:
        return f"{sec:.1f}s"
    if sec < 3600:
        return f"{sec / 60:.1f}m"
    return f"{sec / 3600:.1f}h"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline time heuristics (local CPU)")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog/shows_v1.json")
    parser.add_argument("--subs-dir", type=Path, default=ROOT / "data/subs")
    parser.add_argument("--sample-n", type=int, default=10)
    parser.add_argument("--embed-batch", type=int, default=64, help="Simulated embed batch (CPU)")
    parser.add_argument("--skip-embed", action="store_true", help="Use throughput constants (no model load)")
    args = parser.parse_args()

    shows = load_catalog(args.catalog)
    cat = catalog_summary(shows)
    episodes_target = cat["episodes_total"]

    sample = find_sample_srts(args.subs_dir, args.sample_n)
    if not sample:
        print("No SRT files found. Download subs first or place Archer SRTs in 29thMay/", file=sys.stderr)
        sys.exit(1)

    # Parse timing
    t0 = time.perf_counter()
    chunks = build_chunks(sample, show_id="benchmark", show_title="Benchmark")
    parse_sec = time.perf_counter() - t0
    per_file_parse = parse_sec / len(sample)
    chunks_per_file = len(chunks) / len(sample)

    # Embed timing (CPU sample — small batch)
    embed_sec = None
    embed_per_chunk = None
    embed_source = "fallback_constant"
    if args.skip_embed:
        embed_per_chunk = 0.0033
    else:
        try:
            from quote_lib.search.embedder import Embedder

            emb = Embedder()
            texts = [c.text_embed for c in chunks[: min(200, len(chunks))]]
            t1 = time.perf_counter()
            emb.encode(texts, batch_size=args.embed_batch)
            embed_sec = time.perf_counter() - t1
            embed_per_chunk = embed_sec / len(texts)
            embed_source = "measured"
        except Exception as exc:
            print(f"WARN embed benchmark skipped: {exc}", file=sys.stderr)
            embed_per_chunk = 0.0033

    est_chunks_sample = int(episodes_target * chunks_per_file)
    # Calibrate from Archer full index when available (deduped episode count)
    archer_meta = ROOT / "data/index/archer_full/meta.json"
    archer_manifest = ROOT / "data/processed/manifest/episodes.csv"
    chunks_per_episode_calibrated = None
    if archer_meta.is_file() and archer_manifest.is_file():
        meta = json.loads(archer_meta.read_text(encoding="utf-8"))
        ep_lines = sum(1 for _ in archer_manifest.open(encoding="utf-8")) - 1
        if ep_lines > 0:
            chunks_per_episode_calibrated = meta["chunk_count"] / ep_lines

    chunks_per_ep = chunks_per_episode_calibrated or chunks_per_file
    est_chunks = int(episodes_target * chunks_per_ep)
    est_parse_total = per_file_parse * episodes_target
    est_embed_cpu = (embed_per_chunk or 0) * est_chunks

    # GPU heuristic: L40S/4090 typically 15–40x faster than laptop CPU for MiniLM
    gpu_speedup = 25.0
    est_embed_gpu = est_embed_cpu / gpu_speedup if embed_per_chunk else None

    # Index size
    emb_bytes = est_chunks * 384 * 4
    chunks_jsonl_bytes = est_chunks * 450  # rough bytes per json line

    report = {
        "catalog": cat,
        "sample": {
            "files": len(sample),
            "chunks": len(chunks),
            "chunks_per_file": round(chunks_per_file, 1),
            "chunks_per_episode_archer_calibrated": round(chunks_per_ep, 1),
        },
        "observed_local_cpu": {
            "parse_sec_per_file": round(per_file_parse, 3),
            "parse_total_est": fmt_seconds(est_parse_total),
            "embed_sec_per_chunk_cpu": round(embed_per_chunk, 5) if embed_per_chunk else None,
            "embed_total_est_cpu": fmt_seconds(est_embed_cpu) if embed_per_chunk else "n/a",
            "embed_benchmark_source": embed_source,
        },
        "projections": {
            "estimated_chunks": est_chunks,
            "embed_total_est_gpu_l40s": fmt_seconds(est_embed_gpu) if est_embed_gpu else "n/a",
            "gpu_speedup_assumed": gpu_speedup,
            "embeddings_npy_mb": round(emb_bytes / 1e6, 1),
            "chunks_jsonl_mb": round(chunks_jsonl_bytes / 1e6, 1),
            "index_total_mb_approx": round((emb_bytes + chunks_jsonl_bytes) / 1e6, 1),
        },
        "recommendations": [
            "Parse/chunk locally — typically minutes for ~572 episodes.",
            "Embed on RunPod GPU (L40S or 4090); MiniLM is tiny vs translation workloads.",
            "Use EMBED_BATCH_SIZE=512–1024 on GPU; sentence-transformers batches internally.",
            "Railway: plan ~16GB RAM if loading full numpy index (~700MB–1GB for 4 shows).",
        ],
    }

    out_path = ROOT / "data/processed/stats/pipeline_estimate.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
