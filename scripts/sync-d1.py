#!/usr/bin/env python3
"""Push local SQLite queue state to Cloudflare D1."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lfr.db.connection import get_connection, init_db  # noqa: E402

DB_NAME = "lookingforroom-queue"
SCHEMA = ROOT / "schema" / "d1.sql"


def sql_quote(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def build_sync_sql() -> str:
    init_db()
    statements = ["DELETE FROM applications;", "DELETE FROM listing_flags;"]

    with get_connection() as conn:
        apps = conn.execute(
            """
            SELECT listing_id, status, notes, channel, sent_at, replied_at, toured_at,
                   rejected_at, skipped_at, created_at, updated_at
            FROM applications
            WHERE status != 'accepted'
            """
        ).fetchall()
        for row in apps:
            statements.append(
                "INSERT INTO applications "
                "(listing_id, status, notes, channel, sent_at, replied_at, toured_at, "
                "rejected_at, skipped_at, created_at, updated_at) VALUES ("
                f"{sql_quote(row['listing_id'])}, {sql_quote(row['status'])}, "
                f"{sql_quote(row['notes'] or '')}, {sql_quote(row['channel'])}, "
                f"{sql_quote(row['sent_at'])}, {sql_quote(row['replied_at'])}, "
                f"{sql_quote(row['toured_at'])}, {sql_quote(row['rejected_at'])}, "
                f"{sql_quote(row['skipped_at'])}, {sql_quote(row['created_at'])}, "
                f"{sql_quote(row['updated_at'])});"
            )

        flags = conn.execute(
            """
            SELECT l.id AS listing_id, l.liked, COALESCE(s.is_scam_likely, 0) AS is_scam_likely
            FROM listings l
            LEFT JOIN scores s ON s.listing_id = l.id
            WHERE l.liked = 1 OR COALESCE(s.is_scam_likely, 0) = 1
            """
        ).fetchall()
        now = "datetime('now')"
        for row in flags:
            statements.append(
                "INSERT INTO listing_flags (listing_id, liked, is_scam_likely, updated_at) VALUES ("
                f"{sql_quote(row['listing_id'])}, {int(row['liked'] or 0)}, "
                f"{int(row['is_scam_likely'] or 0)}, {now});"
            )

    return "\n".join(statements) + "\n"


def run_wrangler(args: list[str]) -> None:
    cmd = ["npx", "wrangler", "d1", *args]
    subprocess.run(cmd, cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync local queue state to Cloudflare D1")
    parser.add_argument("--local", action="store_true", help="Write to local D1 only")
    args = parser.parse_args(argv)

    if not SCHEMA.exists():
        print(f"Missing schema: {SCHEMA}", file=sys.stderr)
        return 1

    target = ["--local"] if args.local else ["--remote"]
    print(f"Migrating D1 schema ({'local' if args.local else 'remote'})...")
    run_wrangler(["execute", DB_NAME, *target, f"--file={SCHEMA}"])
    for col in ("replied_at", "toured_at", "rejected_at", "skipped_at"):
        subprocess.run(
            [
                "npx",
                "wrangler",
                "d1",
                "execute",
                DB_NAME,
                *target,
                "--command",
                f"ALTER TABLE applications ADD COLUMN {col} TEXT",
            ],
            cwd=ROOT,
            check=False,
        )

    sql = build_sync_sql()
    sync_file = ROOT / ".run" / "d1-sync.sql"
    sync_file.parent.mkdir(parents=True, exist_ok=True)
    sync_file.write_text(sql, encoding="utf-8")

    print(f"Uploading queue state ({sql.count(chr(10))} statements)...")
    run_wrangler(["execute", DB_NAME, *target, f"--file={sync_file}"])
    print("D1 sync complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())