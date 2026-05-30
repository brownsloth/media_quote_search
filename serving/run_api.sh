#!/usr/bin/env bash
# Run Quote Memory API from repo root (no cd into serving/api).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/src"
export SERVE_INDEX_DIR="${SERVE_INDEX_DIR:-$ROOT/data/index/archer_full}"
export NETFLIX_MAPPING_PATH="${NETFLIX_MAPPING_PATH:-$ROOT/data/netflix/archer_episodes.json}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:8888,http://127.0.0.1:8888,http://localhost:8000,http://localhost:8001}"

PORT="${PORT:-8001}"

if [[ ! -f "$SERVE_INDEX_DIR/embeddings.npy" ]]; then
  echo "Missing index: $SERVE_INDEX_DIR/embeddings.npy"
  echo "Build with: bash scripts/search/run_build_full_index.sh"
  exit 1
fi

echo "Index:  $SERVE_INDEX_DIR"
echo "API:    http://127.0.0.1:${PORT}"
echo "Health: http://127.0.0.1:${PORT}/health"
echo "(First search loads models — may take 30–60s)"

pip install -q -r serving/api/requirements.txt 2>/dev/null || true
exec python -m uvicorn app:app --host 0.0.0.0 --port "$PORT" --app-dir serving/api
