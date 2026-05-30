#!/usr/bin/env bash
# End-to-end local ingest for catalog v1 (parse only; embed on RunPod).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

echo "=== Step 0: pipeline time estimate (local CPU sample) ==="
python scripts/ingest/estimate_pipeline_time.py --sample-n 10

echo ""
echo "=== Step 1: download subtitles from my-subs.co ==="
echo "Smoke test (2 eps per show, ~1 min/show with 10s countdown):"
echo "  python scripts/ingest/download_mysubs.py --max-episodes 2"
echo ""
echo "Full download (~572 eps, ~2h with 10s countdown per file):"
echo "  python scripts/ingest/download_mysubs.py"
echo ""
echo "(OpenSubtitles API alternative if needed:"
echo "  python scripts/ingest/download_opensubtitles.py)"
echo ""
echo "=== Step 2: parse all shows -> unified chunks.jsonl ==="
python scripts/ingest/parse_catalog.py

echo ""
echo "=== Step 3: embed on RunPod GPU ==="
echo "  bash scripts/runpod/build_universal_index.sh"
echo "  (sync data/processed/universal + data/index via Dropbox)"
