#!/usr/bin/env bash
# Fetch Archer SxxExx → Netflix /watch/ IDs via Shakti API.
# If scripted POST gets HTTP 421, use browser_fetch_archer_episodes.js instead.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH=src

if [[ -z "${NETFLIX_COOKIE:-}" && ( -z "${NETFLIX_ID:-}" || -z "${SECURE_NETFLIX_ID:-}" ) ]]; then
  echo "Set Netflix session env vars:"
  echo "  export NETFLIX_ID='...'"
  echo "  export SECURE_NETFLIX_ID='...'"
  echo "Or: export NETFLIX_COOKIE='NetflixId=...; SecureNetflixId=...'"
  echo ""
  echo "Or skip cookies — use browser script: scripts/data/browser_fetch_archer_episodes.js"
  exit 1
fi

python -u scripts/data/fetch_archer_netflix_ids.py "$@" || {
  echo ""
  echo "Scripted fetch failed? Use browser (works when Netflix blocks curl/python):"
  echo "  1. Chrome → netflix.com (logged in) → DevTools Console"
  echo "  2. Paste: scripts/data/browser_fetch_archer_episodes.js"
  echo "  3. python scripts/data/import_netflix_mapping.py ~/Downloads/archer_episodes.json"
  exit 1
}

echo ""
echo "Re-upload artifacts if deploying:"
echo "  bash serving/package_artifacts.sh"
