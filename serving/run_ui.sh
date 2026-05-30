#!/usr/bin/env bash
# Serve Quote Memory UI only (pair with serving/run_api.sh on PORT=8001).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8888}"
echo "Quote Memory UI: http://127.0.0.1:${PORT}/"
echo "Set config.js QUOTE_MEMORY_API to your API (default http://localhost:8001)"
cd "$ROOT/serving/web"
exec python3 -m http.server "$PORT"
