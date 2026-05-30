#!/usr/bin/env python3
"""Audit raw .srt files under a directory tree."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quote_lib.parse.audit import audit_srt_directory
from quote_lib.parse.stats import summarize_ints


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit subtitle files.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "29thMay" / "Archer",
        help="Directory containing .srt files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "audit",
        help="Where to write audit outputs",
    )
    args = parser.parse_args()

    rows = audit_srt_directory(args.input_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.output_dir / "file_audit.csv"
    json_path = args.output_dir / "file_audit.json"
    summary_path = args.output_dir / "audit_summary.json"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "path",
                "season",
                "episode",
                "release_group",
                "status",
                "file_size_bytes",
                "cue_count",
                "dialogue_cue_count",
                "duration_ms",
                "has_watermark",
                "parse_error_count",
                "error_message",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)

    json_path.write_text(
        json.dumps([row.__dict__ for row in rows], indent=2),
        encoding="utf-8",
    )

    status_counts = Counter(row.status for row in rows)
    dialogue_counts = [row.dialogue_cue_count for row in rows if row.status == "valid_srt"]
    summary = {
        "input_dir": str(args.input_dir),
        "files_total": len(rows),
        "status_counts": dict(status_counts),
        "valid_files": status_counts.get("valid_srt", 0),
        "dialogue_cues_per_file": summarize_ints(dialogue_counts).__dict__,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {summary_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
