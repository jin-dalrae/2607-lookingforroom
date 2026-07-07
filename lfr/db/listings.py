"""Listing CRUD."""

from __future__ import annotations

from typing import Any

from lfr.db.connection import _utcnow, get_connection, init_db

def get_listing_by_url(url: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM listings WHERE url = ?",
            (url,),
        ).fetchone()
    return dict(row) if row else None


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
    rental_address: str | None = None,
    source: str = "craigslist",
) -> str:
    """
    Insert or update a listing keyed by URL.

    Returns one of: 'new', 'updated', 'unchanged'.
    """
    now = _utcnow()
    existing = get_listing_by_url(url)
    if existing is None and listing_id:
        existing_by_id = get_listing_by_id(listing_id)
        if existing_by_id is not None:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE listings SET url = ? WHERE id = ?",
                    (url, listing_id),
                )
                conn.commit()
            existing = {**existing_by_id, "url": url}

    def _resolved_move_in_date(row: dict[str, Any]) -> str:
        from lfr.listings.move_in import resolve_move_in_date_storage

        return resolve_move_in_date_storage(row)

    with get_connection() as conn:
        if existing is None:
            row_snapshot: dict[str, Any] = {
                "title": title,
                "description": description,
                "first_seen": now,
                "last_seen": now,
            }
            stored_move_in = (
                move_in_date
                if move_in_date
                else _resolved_move_in_date(row_snapshot)
            )
            conn.execute(
                """
                INSERT INTO listings (
                    id, url, title, price, neighborhood, description,
                    move_in_date, posted_at, rental_address, first_seen, last_seen, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing_id,
                    url,
                    title,
                    price,
                    neighborhood,
                    description,
                    stored_move_in,
                    posted_at,
                    rental_address,
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
        elif description is not None and description != existing["description"]:
            row_snapshot = {**dict(existing), **updates}
            resolved_move_in = _resolved_move_in_date(row_snapshot)
            if resolved_move_in != (existing.get("move_in_date") or ""):
                updates["move_in_date"] = resolved_move_in
                changed = True
        if posted_at is not None:
            from lfr.listings.dates import is_estimated_posted

            if is_estimated_posted(existing) or posted_at != existing.get("posted_at"):
                updates["posted_at"] = posted_at
                changed = True
        if rental_address is not None and rental_address != existing["rental_address"]:
            updates["rental_address"] = rental_address
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


def get_listings_batch(*, offset: int = 0, limit: int = 20) -> list[dict[str, Any]]:
    """Return one page of listings for batched rescoring."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM listings
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


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


def set_listing_liked(listing_id: str, liked: bool) -> bool | None:
    """Set liked flag on a listing. Returns new state, or None if missing."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, liked FROM listings WHERE id = ?",
            (listing_id,),
        ).fetchone()
        if row is None:
            return None
        value = 1 if liked else 0
        conn.execute(
            "UPDATE listings SET liked = ? WHERE id = ?",
            (value, listing_id),
        )
        conn.commit()
    return liked


def toggle_listing_liked(listing_id: str) -> bool | None:
    """Flip liked flag. Returns new state, or None if listing missing."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT liked FROM listings WHERE id = ?",
            (listing_id,),
        ).fetchone()
        if row is None:
            return None
        liked = not bool(row["liked"])
        conn.execute(
            "UPDATE listings SET liked = ? WHERE id = ?",
            (1 if liked else 0, listing_id),
        )
        conn.commit()
    return liked


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
