"""Shared SQLite helpers for the room-finding tool."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import SEARCH_CRITERIA

DB_PATH = Path(__file__).parent / "listings.db"

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

        _migrate_scores_table(conn)
        _init_applications_table(conn)
        _init_mail_messages_table(conn)
        conn.commit()


def init_pipeline_tables() -> None:
    """Alias used by scout.py / run.py."""
    init_db()


def get_unscored(limit: int = 20) -> list[dict[str, Any]]:
    """Alias for get_unscored_listings."""
    return get_unscored_listings(limit=limit)


def get_listing_by_url(url: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM listings WHERE url = ?",
            (url,),
        ).fetchone()


def upsert_listing(
    *,
    listing_id: str,
    url: str,
    title: str | None = None,
    price: int | None = None,
    neighborhood: str | None = None,
    description: str | None = None,
    move_in_date: str | None = None,
    posted_at: str | None = None,
    source: str = "craigslist",
) -> str:
    """
    Insert or update a listing keyed by URL.

    Returns one of: 'new', 'updated', 'unchanged'.
    """
    now = _utcnow()
    existing = get_listing_by_url(url)

    with get_connection() as conn:
        if existing is None:
            conn.execute(
                """
                INSERT INTO listings (
                    id, url, title, price, neighborhood, description,
                    move_in_date, posted_at, first_seen, last_seen, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing_id,
                    url,
                    title,
                    price,
                    neighborhood,
                    description,
                    move_in_date,
                    posted_at,
                    now,
                    now,
                    source,
                ),
            )
            conn.commit()
            return "new"

        changed = False
        updates: dict[str, Any] = {"last_seen": now}

        if listing_id and listing_id != existing["id"]:
            updates["id"] = listing_id
            changed = True
        if title is not None and title != existing["title"]:
            junk_titles = {"notifications", "notification", "facebook marketplace listing"}
            new_low = title.strip().lower()
            old_low = (existing["title"] or "").strip().lower()
            if new_low in junk_titles and old_low and old_low not in junk_titles:
                pass
            else:
                updates["title"] = title
                changed = True
        if price is not None and price != existing["price"]:
            updates["price"] = price
            changed = True
        if neighborhood is not None and neighborhood != existing["neighborhood"]:
            updates["neighborhood"] = neighborhood
            changed = True
        if description is not None and description != existing["description"]:
            updates["description"] = description
            changed = True
        if move_in_date is not None and move_in_date != existing["move_in_date"]:
            updates["move_in_date"] = move_in_date
            changed = True
        if posted_at is not None and posted_at != existing["posted_at"]:
            updates["posted_at"] = posted_at
            changed = True

        set_clause = ", ".join(f"{col} = ?" for col in updates)
        values = list(updates.values()) + [url]
        conn.execute(
            f"UPDATE listings SET {set_clause} WHERE url = ?",
            values,
        )
        conn.commit()
        return "updated" if changed else "unchanged"


def get_all_listings(limit: int | None = None) -> list[dict[str, Any]]:
    """Return all listings, optionally capped."""
    init_db()
    with get_connection() as conn:
        if limit is not None:
            rows = conn.execute(
                """
                SELECT * FROM listings
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM listings
                ORDER BY last_seen DESC
                """
            ).fetchall()
    return [dict(r) for r in rows]


def get_unscored_listings(limit: int = 20) -> list[dict[str, Any]]:
    """Return listings not yet scored by the intelligence layer."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.*
            FROM listings l
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE s.listing_id IS NULL
            ORDER BY l.last_seen DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_score(
    listing_id: str,
    score: int,
    is_private_room: bool,
    is_scam_likely: bool,
    move_in_compatible: bool,
    flags: list[str] | dict[str, Any],
    reasoning: str,
) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scores
                (listing_id, score, is_private_room, is_scam_likely,
                 move_in_compatible, flags_json, reasoning, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing_id,
                max(0, min(100, int(score))),
                int(is_private_room),
                int(is_scam_likely),
                int(move_in_compatible),
                json.dumps(flags),
                reasoning[:500],
                _utcnow(),
            ),
        )
        conn.commit()


def _is_short_term_listing(flags_json: str | None) -> bool:
    if not flags_json:
        return False
    try:
        parsed = json.loads(flags_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    if parsed.get("short_term_reject"):
        return True
    rent_period = str(parsed.get("rent_period") or "").lower()
    return rent_period in ("weekly", "daily", "sublet")


def mark_listing_unavailable(
    listing_ref: str,
    *,
    reason: str = "not available",
) -> dict[str, Any] | None:
    """Mark a listing dead (rented/gone). Excluded from future rankings."""
    init_db()
    listing = get_listing_by_url(listing_ref) if listing_ref.startswith("http") else get_listing_by_id(listing_ref)
    if listing is None and listing_ref.startswith("http"):
        path = listing_ref.rstrip("/").split("/")[-1]
        listing = get_listing_by_id(path)
    if listing is None:
        return None

    app = upsert_application_draft(
        listing["id"],
        draft_text="",
        status="rejected",
    )
    update_application_status(app["id"], "rejected", notes=reason)
    return listing


def get_matching_listings(
    limit: int = 15,
    exclude_scams: bool = True,
    exclude_short_term: bool = True,
    exclude_unavailable: bool = True,
) -> list[dict[str, Any]]:
    """Hard-filter: late Jul–Aug 18, $800–$1000, location rules; sort by price band fit."""
    from match import listing_matches_criteria, sort_matches

    init_db()
    scam_clause = "AND s.is_scam_likely = 0" if exclude_scams else ""
    dead_clause = (
        """
        AND l.id NOT IN (
            SELECT listing_id FROM applications
            WHERE status IN ('rejected', 'accepted')
        )
        """
        if exclude_unavailable
        else ""
    )
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM listings l
            INNER JOIN scores s ON l.id = s.listing_id
            WHERE 1=1 {scam_clause} {dead_clause}
            ORDER BY CASE WHEN l.price IS NULL THEN 1 ELSE 0 END, l.price ASC, l.title ASC
            LIMIT 500
            """,
        ).fetchall()

    results = [
        r
        for r in (dict(row) for row in rows)
        if listing_matches_criteria(
            r,
            exclude_scams=exclude_scams,
            exclude_short_term=exclude_short_term,
        )
    ]
    return sort_matches(results)[:limit]


def get_ranked_listings(
    limit: int = 15,
    exclude_scams: bool = True,
    exclude_short_term: bool = True,
    exclude_unavailable: bool = True,
    august_priority: bool = True,
    august_only: bool = False,
) -> list[dict[str, Any]]:
    """Alias for get_matching_listings (score/august flags ignored)."""
    _ = august_priority, august_only
    return get_matching_listings(
        limit=limit,
        exclude_scams=exclude_scams,
        exclude_short_term=exclude_short_term,
        exclude_unavailable=exclude_unavailable,
    )


def get_pool_listings(
    limit: int = 150,
    *,
    exclude_scams: bool = True,
    exclude_short_term: bool = True,
) -> list[dict[str, Any]]:
    """Scored listings under budget (no move-in hard filter)."""
    from match import _flags_payload, price_within_budget, sort_matches

    init_db()
    scam_clause = "AND s.is_scam_likely = 0" if exclude_scams else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                l.posted_at, l.first_seen, l.last_seen,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM listings l
            INNER JOIN scores s ON l.id = s.listing_id
            WHERE 1=1 {scam_clause}
            ORDER BY s.score DESC, l.price ASC
            LIMIT 500
            """,
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        listing = dict(row)
        if exclude_scams and listing.get("is_scam_likely"):
            continue
        payload = _flags_payload(listing.get("flags_json"))
        if exclude_short_term:
            if payload.get("short_term_reject"):
                continue
            if str(payload.get("rent_period") or "").lower() in ("weekly", "daily", "sublet"):
                continue
        room_flags = payload.get("flags") or []
        if not isinstance(room_flags, list):
            room_flags = [str(room_flags)]
        if "shared_bedroom_reject" in room_flags or "sro_reject" in room_flags:
            continue
        if not price_within_budget(listing):
            continue
        from match import is_excluded_location

        if is_excluded_location(listing):
            continue
        if "location_reject" in room_flags:
            continue
        if "office_sublease_reject" in room_flags:
            continue
        results.append(listing)

    return sort_matches(results)[:limit]


def get_listings_with_queue_applications(
    *,
    statuses: tuple[str, ...] = ("skipped", "sent", "replied", "toured", "draft"),
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Listings that have an application in a queue-visible status."""
    init_db()
    placeholders = ",".join("?" for _ in statuses)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                l.posted_at, l.first_seen, l.last_seen,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM applications a
            INNER JOIN listings l ON l.id = a.listing_id
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE a.status IN ({placeholders})
            ORDER BY a.updated_at DESC
            LIMIT ?
            """,
            (*statuses, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_queue_export_listings(*, pool_limit: int = 500) -> list[dict[str, Any]]:
    """Pool listings plus any with queue application rows (e.g. skipped after filter)."""
    pool = get_pool_listings(limit=pool_limit, exclude_scams=True)
    seen = {row["id"] for row in pool}
    rows = list(pool)
    for row in get_listings_with_queue_applications(limit=pool_limit):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    return rows


def get_top_listings(limit: int = 15) -> list[dict[str, Any]]:
    """Alias for run.py compatibility."""
    return get_ranked_listings(limit=limit, exclude_scams=True)


def count_listings() -> int:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM listings").fetchone()
    return int(row["n"]) if row else 0


def get_listing_by_id(listing_id: str) -> dict[str, Any] | None:
    """Return a listing row by primary key."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM listings WHERE id = ?",
            (listing_id,),
        ).fetchone()
    return dict(row) if row else None


def get_ranked_listing_at_position(
    position: int,
    *,
    exclude_scams: bool = True,
    exclude_short_term: bool = True,
) -> dict[str, Any] | None:
    """Return the Nth ranked listing (1-indexed)."""
    if position < 1:
        return None
    rows = get_ranked_listings(
        limit=position,
        exclude_scams=exclude_scams,
        exclude_short_term=exclude_short_term,
    )
    return rows[position - 1] if len(rows) >= position else None


def _listing_with_score(listing_id: str) -> dict[str, Any] | None:
    """Return listing joined with score fields."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM listings l
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE l.id = ?
            """,
            (listing_id,),
        ).fetchone()
    return dict(row) if row else None


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
    app = get_application_by_listing_id(listing_id)
    if app is None:
        return None

    combined_notes = _format_reply_notes(notes, email_meta)
    now = _utcnow()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE applications
            SET status = 'replied', notes = ?, updated_at = ?
            WHERE listing_id = ? AND status IN ('sent', 'replied')
            """,
            (combined_notes, now, listing_id),
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


def seed_test_listings() -> int:
    """Insert sample listings when scout hasn't run yet."""
    samples = [
        {
            "listing_id": "test-mission-private",
            "title": "Private room in Mission — utilities included",
            "price": 1250,
            "neighborhood": "Mission District",
            "url": "https://example.com/listing/mission-private-1",
            "description": (
                "Furnished private bedroom in 3BR flat. Available mid-August. "
                "Shared kitchen/bath with 2 roommates."
            ),
            "move_in_date": "2026-08-15",
            "source": "test",
        },
        {
            "listing_id": "test-soma-scam",
            "title": "Shared bedroom SOMA — $450!!! Wire only",
            "price": 450,
            "neighborhood": "SoMa",
            "url": "https://example.com/listing/soma-scam-1",
            "description": (
                "Amazing deal! Send deposit via wire transfer before viewing. "
                "Shared bed in studio."
            ),
            "move_in_date": "ASAP",
            "source": "test",
        },
        {
            "listing_id": "test-excelsior-private",
            "title": "Sunny private room near Daly City border",
            "price": 1100,
            "neighborhood": "Excelsior / Daly City border",
            "url": "https://example.com/listing/excelsior-private-1",
            "description": (
                "Private room in quiet house. Move-in flexible late July "
                "through September. Street parking."
            ),
            "move_in_date": "2026-08-20",
            "source": "test",
        },
    ]
    created = 0
    for item in samples:
        if get_listing_by_url(item["url"]) is None:
            upsert_listing(**item)
            created += 1
    return created