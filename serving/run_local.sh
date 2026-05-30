#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"
export SERVE_ARTIFACTS_DIR="$ROOT/serving/artifacts"
export SERVE_INDEX_DIR="${SERVE_INDEX_DIR:-$ROOT/data/index/archer_full}"
export NETFLIX_MAPPING_PATH="${NETFLIX_MAPPING_PATH:-$ROOT/data/netflix/archer_episodes.json}"
export CORS_ORIGINS="http://localhost:8888,http://127.0.0.1:8888,http://localhost:8000"

if [[ ! -f "$SERVE_INDEX_DIR/embeddings.npy" ]]; then
  if [[ -f "$SERVE_ARTIFACTS_DIR/index/embeddings.npy" ]]; then
    export SERVE_INDEX_DIR="$SERVE_ARTIFACTS_DIR/index"
  else
    echo "No index at $SERVE_INDEX_DIR — using data/index/archer_full or run download_artifacts.py"
    export SERVE_INDEX_DIR="$ROOT/data/index/archer_full"
  fi
fi

echo "Index: $SERVE_INDEX_DIR"
echo "Starting API on :8000 ..."
cd serving/api
pip install -q -r requirements.txt 2>/dev/null || true
uvicorn app:app --host 0.0.0.0 --port 8000 &
API_PID=$!

cd "$ROOT/serving/web"
python3 -m http.server 8888 &
WEB_PID=$!

echo "Web UI: http://localhost:8888"
echo "API:    http://localhost:8000/health"
echo "Ctrl+C to stop"

trap "kill $API_PID $WEB_PID 2>/dev/null" EXIT
wait
