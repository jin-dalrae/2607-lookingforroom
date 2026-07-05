#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_NAME="${PAGES_PROJECT_NAME:-2607-lookingforroom}"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

export DETAIL_BACKFILL_LIMIT="${DETAIL_BACKFILL_LIMIT:-0}"
export FB_TITLE_BACKFILL_LIMIT="${FB_TITLE_BACKFILL_LIMIT:-0}"
export POSTED_BACKFILL_LIMIT="${POSTED_BACKFILL_LIMIT:-0}"

echo "Pulling latest online queue state into local DB..."
"$PYTHON" "$ROOT/scripts/pull-d1.py" || true

echo "Exporting apply queue..."
"$PYTHON" listings_page.py

echo "Syncing queue state to Cloudflare D1..."
"$PYTHON" "$ROOT/scripts/sync-d1.py"

echo "Deploying to Cloudflare Pages ($PROJECT_NAME)..."
npx wrangler pages deploy \
  --project-name="$PROJECT_NAME" \
  --commit-dirty=true

echo "Done. Online UI: https://${PROJECT_NAME}.pages.dev"