#!/usr/bin/env bash
# End-to-end batch: translate → full index → expand eval → optional guardrail tune.
# Run steps individually if you prefer; translation and index are the slow parts.
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "=== Step 1/4: Translate known Spanish episodes ==="
bash scripts/ingest/run_translate_known.sh

echo ""
echo "=== Step 2/4: Build full corpus index ==="
bash scripts/search/run_build_full_index.sh

echo ""
echo "=== Step 3/4: Expand eval queries ==="
bash scripts/eval/run_expand_queries.sh

echo ""
echo "=== Step 4/4: Guardrail tuning (optional — comment out to skip) ==="
export PYTHONPATH=src
python scripts/eval/tune_guardrails.py \
  --index-dir data/index/archer_full \
  --queries-path eval/queries_archer_variants.jsonl \
  --quick

echo ""
echo "All done. Best guardrail config (if tuned): data/processed/stats/guardrail_config.json"
