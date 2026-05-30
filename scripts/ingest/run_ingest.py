#!/usr/bin/env python3
"""Run audit -> parse/store -> corpus stats."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INGEST = ROOT / "scripts" / "ingest"


def run(script: str, *args: str) -> None:
    cmd = [sys.executable, str(INGEST / script), *args]
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full ingest pipeline.")
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
    parser.add_argument("--context-window", type=int, default=5)
    parser.add_argument("--only-valid", action="store_true")
    args = parser.parse_args()

    audit_out = args.output_dir / "audit"
    stats_out = args.output_dir / "stats"

    run(
        "audit_srts.py",
        "--input-dir",
        str(args.input_dir),
        "--output-dir",
        str(audit_out),
    )
    parse_args = [
        "parse_and_store.py",
        "--input-dir",
        str(args.input_dir),
        "--output-dir",
        str(args.output_dir),
        "--context-window",
        str(args.context_window),
    ]
    if args.only_valid:
        parse_args.append("--only-valid")
    run(*parse_args)
    run(
        "corpus_stats.py",
        "--chunks-path",
        str(args.output_dir / "chunks.jsonl"),
        "--cues-path",
        str(args.output_dir / "cues.jsonl"),
        "--output-dir",
        str(stats_out),
    )


if __name__ == "__main__":
    main()
