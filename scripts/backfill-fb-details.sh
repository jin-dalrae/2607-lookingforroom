#!/usr/bin/env bash
# Scrape Facebook listing pages for rows missing location, description, or move-in.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

LIMIT="${1:-50}"
ALL_FLAG=""
if [[ "${2:-}" == "--all" ]]; then
  ALL_FLAG="--all"
fi

echo "Fetching Facebook details for up to ${LIMIT} listing(s) (~30s each)..."
"$PYTHON" -m lfr.scout.facebook backfill --limit "$LIMIT" $ALL_FLAG

DETAIL_BACKFILL_LIMIT=0 POSTED_BACKFILL_LIMIT=0 FB_TITLE_BACKFILL_LIMIT=0 "$PYTHON" listings_page.py
echo "Queue export updated."