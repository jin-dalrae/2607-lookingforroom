"""Processed inbound mail deduplication."""

from __future__ import annotations

from lfr.db.connection import _utcnow, get_connection, init_db

def is_mail_message_processed(message_id: str) -> bool:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM mail_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    return row is not None


def record_mail_message(
    *,
    message_id: str,
    from_addr: str,
    subject: str,
    email_date: str,
    snippet: str,
    matched_listing_id: str | None = None,
    match_method: str | None = None,
) -> None:
    """Persist a processed email for dedup and audit."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO mail_messages (
                message_id, from_addr, subject, email_date, snippet,
                matched_listing_id, match_method, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                from_addr,
                subject,
                email_date,
                snippet,
                matched_listing_id,
                match_method,
                _utcnow(),
            ),
        )
        conn.commit()


