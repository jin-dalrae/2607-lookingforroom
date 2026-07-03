"""Queue and export listing queries."""

from __future__ import annotations

from typing import Any

from lfr.db.connection import get_connection, init_db
from lfr.db.scores import get_pool_listings

def get_listings_with_queue_applications(
    *,
    statuses: tuple[str, ...] = (
        "skipped",
        "sent",
        "replied",
        "toured",
        "draft",
        "rejected",
    ),
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
                l.posted_at, l.rental_address, l.liked, l.first_seen, l.last_seen,
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


def get_facebook_card_listings(*, limit: int = 400) -> list[dict[str, Any]]:
    """Facebook listings with card-level scrape data for the apply queue UI."""
    from lfr.listings.dates import is_stale_listing
    from lfr.listings.description import is_junk_facebook_title
    from lfr.listings.location import is_excluded_location, is_fb_search_area_label
    from lfr.pipeline.match import price_within_budget

    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                l.posted_at, l.rental_address, l.liked, l.first_seen, l.last_seen,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM listings l
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE l.source = 'facebook'
              AND l.id NOT IN (
                  SELECT listing_id FROM applications WHERE status = 'rejected'
              )
            ORDER BY l.last_seen DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        listing = dict(row)
        if is_junk_facebook_title(str(listing.get("title") or "")):
            continue
        hood = (listing.get("neighborhood") or "").strip()
        if is_fb_search_area_label(hood) and not (listing.get("rental_address") or "").strip():
            continue
        if listing.get("is_scam_likely"):
            continue
        if not price_within_budget(listing):
            continue
        if is_excluded_location(listing):
            continue
        if is_stale_listing(listing):
            continue
        results.append(listing)
    return results


def get_queue_export_listings(*, pool_limit: int = 500) -> list[dict[str, Any]]:
    """Pool listings plus Facebook card rows and any with queue application rows."""
    pool = get_pool_listings(limit=pool_limit, exclude_scams=True)
    seen = {row["id"] for row in pool}
    rows = list(pool)
    for row in get_facebook_card_listings(limit=pool_limit):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    for row in get_listings_with_queue_applications(limit=pool_limit):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    return rows


