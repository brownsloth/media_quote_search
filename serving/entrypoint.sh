#!/usr/bin/env bash
# Optional Netflix mapping refresh at container start (Railway redeploy picks up new env).
set -euo pipefail
cd /app
export PYTHONPATH=/app/src:/app
export NETFLIX_MAPPING_PATH="${NETFLIX_MAPPING_PATH:-/app/serving/artifacts/netflix/archer_episodes.json}"

if [[ -n "${NETFLIX_ID:-}" && -n "${SECURE_NETFLIX_ID:-}" ]] || [[ -n "${NETFLIX_COOKIE:-}" ]]; then
  if [[ "${NETFLIX_EPISODE_LINKS:-}" =~ ^(1|true|yes)$ ]]; then
    echo "Refreshing Netflix episode map from Shakti ..."
    mkdir -p "$(dirname "$NETFLIX_MAPPING_PATH")"
    if python scripts/data/fetch_archer_netflix_ids.py; then
      echo "Netflix map updated at $NETFLIX_MAPPING_PATH"
    else
      echo "Netflix fetch failed — using show-page links."
    fi
  fi
fi

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
