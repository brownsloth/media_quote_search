#!/usr/bin/env bash
set -euo pipefail
cd /app
export PYTHONPATH=/app/src:/app
export NETFLIX_MAPPING_PATH="${NETFLIX_MAPPING_PATH:-/app/serving/artifacts/netflix/archer_episodes.json}"

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --app-dir /app/serving/api
