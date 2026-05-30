#!/usr/bin/env bash
# Expand eval queries with memory-style variants (typos, paraphrases).
# Run from repo root with conda env active.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH=src

python scripts/eval/expand_queries.py \
  --input eval/queries_archer.jsonl \
  --memory-variants eval/memory_variants.json \
  --output eval/queries_archer_variants.jsonl

echo ""
echo "Expanded eval written to eval/queries_archer_variants.jsonl"
echo "Optional: tune guardrails on the expanded set (slow — loads CE per config):"
echo "  python scripts/eval/tune_guardrails.py --index-dir data/index/archer_full --queries-path eval/queries_archer_variants.jsonl --quick"
