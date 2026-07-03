#!/usr/bin/env bash
# Scrape Facebook listing text for queue rows missing descriptions.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

LIMIT="${1:-8}"
echo "Fetching Facebook details for up to ${LIMIT} queue listing(s) (~30s each)..."
"$PYTHON" -c "
from db import backfill_facebook_details
print(backfill_facebook_details(limit=int('${LIMIT}'), queue_only=True))
"

DETAIL_BACKFILL_LIMIT=0 POSTED_BACKFILL_LIMIT=0 "$PYTHON" listings_page.py
echo "Queue export updated."