#!/usr/bin/env bash
# Translate known Spanish S1 episodes (E04–E10) and patch cues/chunks.
# Requires: transformers, sentencepiece, torch (MarianMT downloads on first run).
# First run: model download ~300MB — watch for "loading MarianMT" lines.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
export HF_HUB_ENABLE_PROGRESS_BARS=1

python -u scripts/ingest/translate_known_episodes.py \
  --input-dir 29thMay/Archer \
  --data-dir data/processed \
  "$@"

echo ""
echo "Done. Rebuild index after this:"
echo "  bash scripts/search/run_build_full_index.sh"
