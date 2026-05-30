#!/usr/bin/env bash
# Embed all processed chunks (S01–S14) into a full-corpus index.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH=src
export PYTHONUNBUFFERED=1

OUT=data/index/archer_full
mkdir -p "$OUT"

python -u scripts/search/build_index.py \
  --chunks-path data/processed/chunks.jsonl \
  --output-dir "$OUT" \
  "$@"

echo ""
echo "Full index at $OUT"
