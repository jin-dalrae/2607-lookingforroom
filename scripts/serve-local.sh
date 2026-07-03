#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STATIC_PORT="${STATIC_PORT:-8765}"
API_PORT="${API_PORT:-8787}"

echo "Exporting queue data..."
python listings_page.py

echo "Starting Apply API on :${API_PORT}..."
python api.py --port "$API_PORT" --host 127.0.0.1 &
API_PID=$!

cleanup() {
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "Serving UI at http://localhost:${STATIC_PORT}/"
python -m http.server "$STATIC_PORT" --directory site