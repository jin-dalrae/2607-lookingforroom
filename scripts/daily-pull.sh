#!/usr/bin/env bash
# Scheduled pull: Craigslist (+ optional Facebook), score, export, Telegram, workers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

WITH_FACEBOOK="${WITH_FACEBOOK:-0}"
TELEGRAM_ALERT="${TELEGRAM_ALERT:-1}"
TELEGRAM_STATUS="${TELEGRAM_STATUS:-1}"
DETAIL_BACKFILL_LIMIT="${DETAIL_BACKFILL_LIMIT:-15}"
FB_TITLE_BACKFILL_LIMIT="${FB_TITLE_BACKFILL_LIMIT:-3}"
POSTED_BACKFILL_LIMIT="${POSTED_BACKFILL_LIMIT:-25}"

echo "=== Daily pull $(date '+%Y-%m-%d %H:%M') ==="

echo "▶ Craigslist scout…"
"$PYTHON" -c "import scout; c=scout.run_poll_cycle(); print(f\"  CL: {c.get('new',0)} new, {c.get('updated',0)} updated\")"

if [[ "$WITH_FACEBOOK" == "1" ]]; then
  echo "▶ Facebook poll (Playwright — needs session)…"
  if "$PYTHON" -c "from facebook_session import session_configured; raise SystemExit(0 if session_configured() else 1)"; then
    "$PYTHON" scout_facebook.py poll
  else
    echo "  skipped — run: python scout_facebook.py login"
  fi
else
  echo "▶ Facebook skipped (set WITH_FACEBOOK=1 to include)"
fi

echo "▶ Filter + rank…"
"$PYTHON" filter.py
"$PYTHON" rank.py

echo "▶ Export queue…"
DETAIL_BACKFILL_LIMIT="$DETAIL_BACKFILL_LIMIT" \
FB_TITLE_BACKFILL_LIMIT="$FB_TITLE_BACKFILL_LIMIT" \
POSTED_BACKFILL_LIMIT="$POSTED_BACKFILL_LIMIT" \
"$PYTHON" listings_page.py

if [[ "$TELEGRAM_ALERT" == "1" ]]; then
  echo "▶ Telegram digest…"
  TELEGRAM_STATUS="$TELEGRAM_STATUS" "$PYTHON" scripts/telegram_digest.py
fi

echo "▶ Restart local workers…"
TELEGRAM_ALERT=0 "$ROOT/scripts/workers.sh" restart

echo "Done."