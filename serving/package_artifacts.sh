#!/usr/bin/env bash
# Package local index + guardrail config and upload to Hugging Face Hub.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPO="${HF_ARTIFACTS_REPO:-1starun8-research/archer-quote-index}"
INDEX_SRC="${1:-data/index/archer_full}"
STAGE="$ROOT/serving/artifacts"

echo "=== Stage artifacts ==="
rm -rf "$STAGE/index"
mkdir -p "$STAGE/index" "$STAGE/netflix"

for f in embeddings.npy chunks.jsonl meta.json; do
  src="$INDEX_SRC/$f"
  if [[ ! -f "$src" ]]; then
    echo "Missing index file: $src"
    echo "Build first: bash scripts/search/run_build_full_index.sh"
    exit 1
  fi
  cp "$src" "$STAGE/index/"
  echo "  index/$f  ($(du -h "$STAGE/index/$f" | cut -f1))"
done

if [[ -f data/processed/stats/guardrail_config.json ]]; then
  cp data/processed/stats/guardrail_config.json "$STAGE/"
  echo "  guardrail_config.json"
fi

cp data/netflix/archer_episodes.json "$STAGE/netflix/" 2>/dev/null || true
echo "  netflix/archer_episodes.json (episodes may be empty — show-page links only)"

echo ""
echo "Uploading to $REPO ..."
# Upload each path explicitly so Hub layout is index/* at repo root (not artifacts/index/*).
hf upload "$REPO" "$STAGE/index/embeddings.npy" "index/embeddings.npy" --repo-type model
hf upload "$REPO" "$STAGE/index/chunks.jsonl" "index/chunks.jsonl" --repo-type model
hf upload "$REPO" "$STAGE/index/meta.json" "index/meta.json" --repo-type model
if [[ -f "$STAGE/guardrail_config.json" ]]; then
  hf upload "$REPO" "$STAGE/guardrail_config.json" "guardrail_config.json" --repo-type model
fi
hf upload "$REPO" "$STAGE/netflix/archer_episodes.json" "netflix/archer_episodes.json" --repo-type model

echo ""
echo "Done. Hub should contain:"
echo "  index/embeddings.npy"
echo "  index/chunks.jsonl"
echo "  index/meta.json"
echo "  guardrail_config.json"
echo "  netflix/archer_episodes.json"
echo ""
echo "Set HF_ARTIFACTS_REPO=$REPO on Railway."
