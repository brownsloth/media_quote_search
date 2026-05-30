#!/usr/bin/env bash
# Build universal quote index on RunPod GPU (Dropbox-synced workspace).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
export HF_HOME="${HF_HOME:-/workspace/huggingface_cache}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME}"
export EMBED_DEVICE="${EMBED_DEVICE:-cuda}"
export EMBED_BATCH_SIZE="${EMBED_BATCH_SIZE:-1024}"

CHUNKS="${CHUNKS:-$ROOT/data/processed/universal/chunks.jsonl}"
OUT="${OUT:-$ROOT/data/index/universal_v1}"
MODEL="${MODEL:-sentence-transformers/all-MiniLM-L6-v2}"

if [[ ! -f "$CHUNKS" ]]; then
  echo "Missing chunks file: $CHUNKS"
  echo "Sync from Dropbox or run parse_catalog.py locally first."
  exit 1
fi

python - <<'PY'
import torch
print(f"torch={torch.__version__} cuda_available={torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"gpu={torch.cuda.get_device_name(0)}")
PY

python scripts/search/build_index.py \
  --chunks-path "$CHUNKS" \
  --output-dir "$OUT" \
  --model "$MODEL" \
  --batch-size "${EMBED_BATCH_SIZE}"

echo "Index written to $OUT"
ls -lh "$OUT"
