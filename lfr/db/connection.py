"""SQLite connection, schema, and migrations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "listings.db"

SCORE_COLUMNS = (
    "listing_id",
    "score",
    "is_private_room",
    "is_scam_likely",
    "move_in_compatible",
    "flags_json",
    "reasoning",
    "scored_at",
)

APPLICATION_STATUSES = (
    "draft",
    "sent",
    "replied",
    "toured",
    "skipped",
    "rejected",
    "accepted",
)

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _migrate_scores_table(conn: sqlite3.Connection) -> None:
    """Ensure scores table has the full intelligence-layer schema."""
    existing = _table_columns(conn, "scores")
    if not existing:
        conn.execute(
            """
            CREATE TABLE scores (
                listing_id TEXT PRIMARY KEY,
                score INTEGER NOT NULL,
                is_private_room INTEGER NOT NULL DEFAULT 0,
                is_scam_likely INTEGER NOT NULL DEFAULT 0,
                move_in_compatible INTEGER NOT NULL DEFAULT 0,
                flags_json TEXT,
                reasoning TEXT,
                scored_at TEXT,
                FOREIGN KEY (listing_id) REFERENCES listings(id)
            )
            """
        )
        return

    migrations = {
        "is_private_room": "INTEGER NOT NULL DEFAULT 0",
        "is_scam_likely": "INTEGER NOT NULL DEFAULT 0",
        "move_in_compatible": "INTEGER NOT NULL DEFAULT 0",
        "flags_json": "TEXT",
        "reasoning": "TEXT",
    }
    for col, typedef in migrations.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE scores ADD COLUMN {col} {typedef}")


APPLICATION_STATUSES = (
    "draft",
    "sent",
    "replied",
    "toured",
    "skipped",
    "rejected",
    "accepted",
)


def _init_mail_messages_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mail_messages (
            message_id TEXT PRIMARY KEY,
            from_addr TEXT,
            subject TEXT,
            email_date TEXT,
            snippet TEXT,
            matched_listing_id TEXT,
            match_method TEXT,
            processed_at TEXT NOT NULL,
            FOREIGN KEY (matched_listing_id) REFERENCES listings(id)
        )
        """
    )


def _init_applications_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            draft_text TEXT,
            notes TEXT,
            channel TEXT,
            sent_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        )
        """
    )
    existing = _table_columns(conn, "applications")
    migrations = {
        "channel": "TEXT",
        "sent_at": "TEXT",
    }
    for col, typedef in migrations.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {typedef}")


def init_db() -> None:
    """Create tables if they do not exist."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                price INTEGER,
                neighborhood TEXT,
                description TEXT,
                move_in_date TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'craigslist'
            )
            """
        )
        cols = _table_columns(conn, "listings")
        if "move_in_date" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN move_in_date TEXT")
        if "posted_at" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN posted_at TEXT")
        if "rental_address" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN rental_address TEXT")
        if "liked" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN liked INTEGER NOT NULL DEFAULT 0")

        _migrate_scores_table(conn)
        _init_applications_table(conn)
        _init_mail_messages_table(conn)
        conn.commit()


def init_pipeline_tables() -> None:
    """Alias used by scout.py / run.py."""
    init_db()


