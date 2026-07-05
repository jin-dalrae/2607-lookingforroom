#!/usr/bin/env python3
"""Pull Cloudflare D1 queue state back into local SQLite."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lfr.db.connection import get_connection, init_db  # noqa: E402

DB_NAME = "lookingforroom-queue"


def query_remote(sql: str) -> list[dict]:
    cmd = [
        "npx",
        "wrangler",
        "d1",
        "execute",
        DB_NAME,
        "--remote",
        "--json",
        "--command",
        sql,
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
    payload = json.loads(proc.stdout)
    if not payload:
        return []
    first = payload[0]
    return list(first.get("results") or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pull D1 queue state into local SQLite")
    parser.parse_args(argv)

    init_db()
    apps = query_remote(
        "SELECT listing_id, status, notes, channel, sent_at, replied_at, toured_at, "
        "rejected_at, skipped_at, created_at, updated_at FROM applications"
    )
    flags = query_remote(
        "SELECT listing_id, liked, is_scam_likely FROM listing_flags"
    )

    with get_connection() as conn:
        for row in apps:
            conn.execute(
                """
                INSERT INTO applications
                    (listing_id, status, draft_text, notes, channel, sent_at, replied_at,
                     toured_at, rejected_at, skipped_at, created_at, updated_at)
                VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(listing_id) DO UPDATE SET
                    status = excluded.status,
                    notes = excluded.notes,
                    channel = excluded.channel,
                    sent_at = excluded.sent_at,
                    replied_at = excluded.replied_at,
                    toured_at = excluded.toured_at,
                    rejected_at = excluded.rejected_at,
                    skipped_at = excluded.skipped_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row["listing_id"],
                    row["status"],
                    row.get("notes") or "",
                    row.get("channel"),
                    row.get("sent_at"),
                    row.get("replied_at"),
                    row.get("toured_at"),
                    row.get("rejected_at"),
                    row.get("skipped_at"),
                    row["created_at"],
                    row["updated_at"],
                ),
            )

        for row in flags:
            conn.execute(
                "UPDATE listings SET liked = ? WHERE id = ?",
                (int(row.get("liked") or 0), row["listing_id"]),
            )
            if int(row.get("is_scam_likely") or 0):
                conn.execute(
                    """
                    INSERT INTO scores (listing_id, score, is_scam_likely, scored_at)
                    VALUES (?, 0, 1, datetime('now'))
                    ON CONFLICT(listing_id) DO UPDATE SET is_scam_likely = 1
                    """,
                    (row["listing_id"],),
                )

        conn.commit()

    print(f"Pulled {len(apps)} application(s) and {len(flags)} flag row(s) from D1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())