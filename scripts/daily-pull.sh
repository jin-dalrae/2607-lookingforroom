#!/usr/bin/env bash
# Scheduled pull: Craigslist (+ optional Facebook), score, export, restart workers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

WITH_FACEBOOK="${WITH_FACEBOOK:-0}"
DETAIL_BACKFILL_LIMIT="${DETAIL_BACKFILL_LIMIT:-15}"
FB_TITLE_BACKFILL_LIMIT="${FB_TITLE_BACKFILL_LIMIT:-3}"
POSTED_BACKFILL_LIMIT="${POSTED_BACKFILL_LIMIT:-25}"

echo "=== Daily pull $(date '+%Y-%m-%d %H:%M') ==="

echo "▶ Craigslist scout…"
"$PYTHON" -c "import lfr.scout.craigslist as scout; c=scout.run_poll_cycle(); print(f\"  CL: {c.get('new',0)} new, {c.get('updated',0)} updated\")"

if [[ "$WITH_FACEBOOK" == "1" ]]; then
  echo "▶ Facebook poll (Playwright — needs session)…"
  if "$PYTHON" -c "from lfr.scout.session import session_configured; raise SystemExit(0 if session_configured() else 1)"; then
    "$PYTHON" -m lfr.scout.facebook poll
  else
    echo "  skipped — run: python scout_facebook.py login"
  fi
else
  echo "▶ Facebook skipped (set WITH_FACEBOOK=1 to include)"
fi

echo "▶ Filter + rank…"
"$PYTHON" -m lfr.score.batch
"$PYTHON" -m lfr.rank

echo "▶ Prune unavailable to-apply / applied posts…"
"$PYTHON" -m lfr.check_urls || true

echo "▶ Export queue…"
DETAIL_BACKFILL_LIMIT="$DETAIL_BACKFILL_LIMIT" \
FB_TITLE_BACKFILL_LIMIT="$FB_TITLE_BACKFILL_LIMIT" \
POSTED_BACKFILL_LIMIT="$POSTED_BACKFILL_LIMIT" \
"$PYTHON" listings_page.py

echo "▶ Restart local workers…"
"$ROOT/scripts/workers.sh" restart

echo "Done."
