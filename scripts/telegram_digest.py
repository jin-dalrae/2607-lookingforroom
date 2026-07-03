#!/usr/bin/env python3
"""Send Telegram digest after queue export or daily pull."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import notify
from db import get_matching_listings, get_queue_export_listings, get_ranked_listings, init_db


def send_telegram_digest(*, status: bool = False) -> int:
    """Push high-score alerts and optional queue status. Returns 0 always."""
    init_db()

    if not notify._telegram_configured():
        print("Telegram: not configured (set TELEGRAM_BOT_TOKEN + chat id or /start bot)")
        return 0

    result = notify.send_digest_alert(
        get_ranked_listings(limit=50, exclude_scams=True),
        channel="telegram",
        min_score=int(os.getenv("TELEGRAM_MIN_SCORE", str(notify.MIN_SCORE_FOR_ALERT))),
        limit=int(os.getenv("TELEGRAM_ALERT_LIMIT", str(notify.TOP_N_ALERT))),
    )
    if result == "sent":
        print("Telegram: high-score digest sent")
    elif result == "dry_run":
        print("Telegram: dry-run (no credentials)")
    else:
        print("Telegram: no new high-score listings to alert")

    if not status:
        return 0

    export = get_queue_export_listings(pool_limit=500)
    matches = get_matching_listings(limit=10, exclude_scams=True)
    fb = sum(1 for row in export if (row.get("source") or "") == "facebook")
    lines = [
        f"Queue: {len(export)} listings ({fb} Facebook)",
        f"Matches (late Jul–Aug 18): {len(matches)}",
    ]
    if matches:
        for index, row in enumerate(matches[:3], start=1):
            price = f"${row['price']}" if row.get("price") else "?"
            title = (row.get("title") or "Untitled")[:55]
            lines.append(f"{index}. {title} — {price}")
            lines.append(f"   {row.get('url', '')}")
    try:
        notify.send_telegram("\n".join(lines))
        print("Telegram: queue status sent")
    except Exception as exc:
        print(f"Telegram: status failed: {exc}", file=sys.stderr)
    return 0


def main() -> int:
    status = os.getenv("TELEGRAM_STATUS", "").strip().lower() in ("1", "true", "yes")
    return send_telegram_digest(status=status)


if __name__ == "__main__":
    raise SystemExit(main())