"""Application tracking and outreach state."""

from __future__ import annotations

import json
from typing import Any

from lfr.db.connection import APPLICATION_STATUSES, _utcnow, get_connection, init_db
from lfr.db.listings import get_listing_by_id, get_listing_by_url
from lfr.db.scores import get_ranked_listings

def get_application_by_listing_id(listing_id: str) -> dict[str, Any] | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
    return dict(row) if row else None


def get_application(application_id: int) -> dict[str, Any] | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
    return dict(row) if row else None


def get_last_draft_application() -> dict[str, Any] | None:
    """Most recently updated application still in draft status."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM applications
            WHERE status = 'draft'
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def get_last_sent_application() -> dict[str, Any] | None:
    """Most recently sent application (by sent_at, then updated_at)."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM applications
            WHERE status = 'sent'
            ORDER BY COALESCE(sent_at, updated_at) DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def list_applications(limit: int = 50) -> list[dict[str, Any]]:
    """Applications with listing metadata, newest first."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                a.id, a.listing_id, a.status, a.draft_text, a.notes,
                a.channel, a.sent_at, a.created_at, a.updated_at,
                l.title, l.price, l.neighborhood, l.url,
                s.score
            FROM applications a
            INNER JOIN listings l ON a.listing_id = l.id
            LEFT JOIN scores s ON l.id = s.listing_id
            ORDER BY a.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_channel_stats() -> dict[str, dict[str, int]]:
    """Application counts grouped by channel and status."""
    init_db()
    by_channel: dict[str, dict[str, int]] = {}
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(channel, 'unknown') AS channel, status, COUNT(*) AS n
            FROM applications
            GROUP BY channel, status
            """
        ).fetchall()
    for row in rows:
        ch = str(row["channel"])
        by_channel.setdefault(ch, {})
        by_channel[ch][str(row["status"])] = int(row["n"])
    return by_channel


def get_application_status_map() -> dict[str, str]:
    """Map listing_id → application status for all queue rows."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT listing_id, status
            FROM applications
            WHERE status != 'accepted'
            """
        ).fetchall()
    return {str(row["listing_id"]): str(row["status"]) for row in rows}


def get_application_stats() -> dict[str, int]:
    """Application counts by status plus unapplied ranked pool size."""
    init_db()
    stats = {status: 0 for status in APPLICATION_STATUSES}
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM applications GROUP BY status"
        ).fetchall()
    for row in rows:
        stats[row["status"]] = int(row["n"])
    stats["total"] = sum(stats[s] for s in APPLICATION_STATUSES)
    stats["awaiting_fresh"] = len(
        get_unapplied_ranked_listings(limit=100, pool_limit=200)
    )
    return stats


def mark_application_sent(
    listing_id: str,
    *,
    channel: str = "craigslist",
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Mark one listing's application as sent. Creates a row if missing."""
    init_db()
    now = _utcnow()
    existing = get_application_by_listing_id(listing_id)

    with get_connection() as conn:
        if existing is None:
            conn.execute(
                """
                INSERT INTO applications
                    (listing_id, status, draft_text, notes, channel, sent_at,
                     created_at, updated_at)
                VALUES (?, 'sent', '', ?, ?, ?, ?, ?)
                """,
                (listing_id, notes, channel, now, now, now),
            )
        elif notes is not None:
            conn.execute(
                """
                UPDATE applications
                SET status = 'sent', channel = ?, sent_at = ?, updated_at = ?,
                    notes = ?
                WHERE listing_id = ?
                """,
                (channel, now, now, notes, listing_id),
            )
        else:
            conn.execute(
                """
                UPDATE applications
                SET status = 'sent', channel = ?, sent_at = ?, updated_at = ?
                WHERE listing_id = ?
                """,
                (channel, now, now, listing_id),
            )
        conn.commit()
    return get_application_by_listing_id(listing_id)


def mark_application_skipped(
    listing_id: str,
    *,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Mark a listing as skipped. Creates a row if missing."""
    init_db()
    now = _utcnow()
    existing = get_application_by_listing_id(listing_id)

    with get_connection() as conn:
        if existing is None:
            conn.execute(
                """
                INSERT INTO applications
                    (listing_id, status, draft_text, notes, channel, created_at, updated_at)
                VALUES (?, 'skipped', '', ?, NULL, ?, ?)
                """,
                (listing_id, notes, now, now),
            )
        elif notes is not None:
            conn.execute(
                """
                UPDATE applications
                SET status = 'skipped', notes = ?, updated_at = ?
                WHERE listing_id = ?
                """,
                (notes, now, listing_id),
            )
        else:
            conn.execute(
                """
                UPDATE applications
                SET status = 'skipped', updated_at = ?
                WHERE listing_id = ?
                """,
                (now, listing_id),
            )
        conn.commit()
    return get_application_by_listing_id(listing_id)


def mark_application_rejected(
    listing_id: str,
    *,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Permanently remove a listing from the apply pool."""
    init_db()
    now = _utcnow()
    existing = get_application_by_listing_id(listing_id)

    with get_connection() as conn:
        if existing is None:
            conn.execute(
                """
                INSERT INTO applications
                    (listing_id, status, draft_text, notes, channel, created_at, updated_at)
                VALUES (?, 'rejected', '', ?, NULL, ?, ?)
                """,
                (listing_id, notes, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE applications
                SET status = 'rejected', notes = COALESCE(?, notes), updated_at = ?
                WHERE listing_id = ?
                """,
                (notes, now, listing_id),
            )
        conn.commit()
    return get_application_by_listing_id(listing_id)


def mark_applications_sent_bulk(
    listing_ids: list[str],
    *,
    channel: str = "craigslist",
) -> int:
    """Mark multiple listings as sent. Returns number updated."""
    count = 0
    for listing_id in listing_ids:
        if mark_application_sent(listing_id, channel=channel):
            count += 1
    return count


def mark_all_drafts_sent(*, channel: str | None = None) -> int:
    """Mark every draft application as sent (catch-up after batch apply)."""
    from channels import default_channel_for_listing

    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT listing_id FROM applications WHERE status = 'draft'"
        ).fetchall()
    count = 0
    for row in rows:
        listing_id = row["listing_id"]
        ch = channel or default_channel_for_listing(get_listing_by_id(listing_id))
        if mark_application_sent(listing_id, channel=ch):
            count += 1
    return count


def mark_ranked_sent(top_n: int, *, channel: str = "craigslist") -> int:
    """Mark top N ranked listings as sent, creating application rows if needed."""
    if top_n < 1:
        return 0
    ranked = get_ranked_listings(limit=top_n, exclude_scams=True)
    listing_ids = [row["id"] for row in ranked]
    return mark_applications_sent_bulk(listing_ids, channel=channel)


def update_application_channel(
    listing_id: str,
    *,
    channel: str,
) -> dict[str, Any] | None:
    """Set outreach channel on an existing application without changing status or sent_at."""
    init_db()
    existing = get_application_by_listing_id(listing_id)
    if existing is None:
        return None
    now = _utcnow()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE applications
            SET channel = ?, updated_at = ?
            WHERE listing_id = ?
            """,
            (channel, now, listing_id),
        )
        conn.commit()
    return get_application_by_listing_id(listing_id)


def update_applications_channel_bulk(
    listing_ids: list[str],
    *,
    channel: str,
) -> int:
    """Update channel on multiple applications. Returns number updated."""
    count = 0
    for listing_id in listing_ids:
        if update_application_channel(listing_id, channel=channel):
            count += 1
    return count


def listing_has_sent_application(listing_id: str) -> bool:
    app = get_application_by_listing_id(listing_id)
    if not app:
        return False
    return app["status"] != "draft"


def upsert_application_draft(
    listing_id: str,
    draft_text: str,
    *,
    status: str = "draft",
    channel: str | None = None,
) -> dict[str, Any]:
    """Create or update an application draft. Returns the application row."""
    if status not in APPLICATION_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    init_db()
    now = _utcnow()
    existing = get_application_by_listing_id(listing_id)
    if channel is None and existing and existing.get("channel"):
        channel = existing["channel"]
    elif channel is None:
        from channels import default_channel_for_listing

        channel = default_channel_for_listing(get_listing_by_id(listing_id))

    with get_connection() as conn:
        if existing is None:
            conn.execute(
                """
                INSERT INTO applications
                    (listing_id, status, draft_text, notes, channel, created_at, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, ?)
                """,
                (listing_id, status, draft_text, channel, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE applications
                SET draft_text = ?, status = ?, channel = ?, updated_at = ?
                WHERE listing_id = ?
                """,
                (draft_text, status, channel, now, listing_id),
            )
        conn.commit()

    app = get_application_by_listing_id(listing_id)
    if app is None:
        raise RuntimeError(f"Failed to save application for {listing_id}")
    return app


def update_application_status(
    application_id: int,
    status: str,
    *,
    notes: str | None = None,
) -> dict[str, Any] | None:
    if status not in APPLICATION_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    init_db()
    now = _utcnow()
    with get_connection() as conn:
        if notes is not None:
            conn.execute(
                """
                UPDATE applications
                SET status = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, notes, now, application_id),
            )
        else:
            conn.execute(
                """
                UPDATE applications
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, now, application_id),
            )
        conn.commit()
    return get_application(application_id)


def _is_unapplied_listing(listing_id: str) -> bool:
    """True when listing has no application or only a draft."""
    app = get_application_by_listing_id(listing_id)
    return app is None or app["status"] == "draft"


def get_unapplied_ranked_listings(
    limit: int = 5,
    *,
    pool_limit: int = 100,
    exclude_scams: bool = True,
    exclude_short_term: bool = True,
) -> list[dict[str, Any]]:
    """Top-ranked listings with no sent application yet."""
    ranked = get_ranked_listings(
        limit=pool_limit,
        exclude_scams=exclude_scams,
        exclude_short_term=exclude_short_term,
    )
    unapplied: list[dict[str, Any]] = []
    for row in ranked:
        if _is_unapplied_listing(row["id"]):
            unapplied.append(row)
        if len(unapplied) >= limit:
            break
    return unapplied


def get_first_unapplied_ranked_listing(
    *,
    exclude_scams: bool = True,
    exclude_short_term: bool = True,
) -> dict[str, Any] | None:
    """Top-ranked listing with no sent application yet."""
    rows = get_unapplied_ranked_listings(
        limit=1,
        exclude_scams=exclude_scams,
        exclude_short_term=exclude_short_term,
    )
    return rows[0] if rows else None


def get_communication_records(limit: int = 200) -> list[dict[str, Any]]:
    """Applications with listing info and latest matched inbox reply."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                a.id AS application_id,
                a.listing_id,
                a.status,
                a.draft_text,
                a.notes,
                a.channel,
                a.sent_at,
                a.created_at,
                a.updated_at,
                l.title,
                l.price,
                l.neighborhood,
                l.url,
                l.source,
                s.score,
                (
                    SELECT m.snippet
                    FROM mail_messages m
                    WHERE m.matched_listing_id = a.listing_id
                    ORDER BY m.processed_at DESC
                    LIMIT 1
                ) AS last_reply_snippet,
                (
                    SELECT m.email_date
                    FROM mail_messages m
                    WHERE m.matched_listing_id = a.listing_id
                    ORDER BY m.processed_at DESC
                    LIMIT 1
                ) AS last_reply_date
            FROM applications a
            INNER JOIN listings l ON a.listing_id = l.id
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE a.status NOT IN ('rejected', 'accepted')
            ORDER BY
                CASE a.status
                    WHEN 'replied' THEN 0
                    WHEN 'sent' THEN 1
                    WHEN 'toured' THEN 2
                    WHEN 'draft' THEN 3
                    ELSE 4
                END,
                COALESCE(a.sent_at, a.updated_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_sent_applications() -> list[dict[str, Any]]:
    """Sent applications with listing metadata (for inbox matching)."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                a.id AS application_id, a.listing_id, a.status, a.notes,
                a.channel, a.sent_at, a.created_at, a.updated_at,
                l.title, l.price, l.neighborhood, l.url,
                s.score
            FROM applications a
            INNER JOIN listings l ON a.listing_id = l.id
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE a.status = 'sent'
            ORDER BY COALESCE(a.sent_at, a.updated_at) DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _format_reply_notes(
    notes: str | None,
    email_meta: dict[str, Any] | None,
) -> str | None:
    if email_meta is None:
        return notes
    payload = {"email": email_meta}
    if notes:
        payload["user_notes"] = notes
    return json.dumps(payload, ensure_ascii=False)


def mark_application_replied(
    listing_id: str,
    *,
    notes: str | None = None,
    email_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Mark a sent application as replied (landlord responded)."""
    init_db()
    existing = get_application_by_listing_id(listing_id)
    combined_notes = _format_reply_notes(notes, email_meta)
    now = _utcnow()
    with get_connection() as conn:
        if existing is None:
            conn.execute(
                """
                INSERT INTO applications
                    (listing_id, status, draft_text, notes, channel, created_at, updated_at)
                VALUES (?, 'replied', '', ?, NULL, ?, ?)
                """,
                (listing_id, combined_notes, now, now),
            )
        elif combined_notes is not None:
            conn.execute(
                """
                UPDATE applications
                SET status = 'replied', notes = ?, updated_at = ?
                WHERE listing_id = ?
                """,
                (combined_notes, now, listing_id),
            )
        else:
            conn.execute(
                """
                UPDATE applications
                SET status = 'replied', updated_at = ?
                WHERE listing_id = ?
                """,
                (now, listing_id),
            )
        conn.commit()
    return get_application_by_listing_id(listing_id)


def mark_application_replied_by_url(
    url: str,
    *,
    notes: str | None = None,
    email_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Mark replied by Craigslist listing URL (or post id slug)."""
    listing = get_listing_by_url(url)
    if listing is None:
        path = url.rstrip("/").split("/")[-1]
        listing = get_listing_by_id(path)
    if listing is None:
        return None
    return mark_application_replied(
        listing["id"],
        notes=notes,
        email_meta=email_meta,
    )


