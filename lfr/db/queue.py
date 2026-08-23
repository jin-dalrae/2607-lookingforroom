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
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Listings that have an application in a queue-visible status.

    Always includes full outreach history (any neighborhood) — location filters only
    apply to new pool / to-apply candidates, never to existing applications.
    """
    init_db()
    placeholders = ",".join("?" for _ in statuses)
    sql = f"""
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
            """
    params: list[Any] = list(statuses)
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_facebook_card_listings(*, limit: int | None = None) -> list[dict[str, Any]]:
    """Facebook listings with card-level scrape data for the apply queue UI."""
    from lfr.listings.dates import is_stale_listing
    from lfr.listings.description import is_junk_facebook_title
    from lfr.listings.location import is_excluded_location
    from lfr.pipeline.match import price_within_budget, queue_excluded_move_in
    from lfr.score.listing_rules import _is_non_residential_listing

    init_db()
    sql = """
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
            """
    params: list[Any] = []
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        listing = dict(row)
        if is_junk_facebook_title(str(listing.get("title") or "")):
            continue
        if _is_non_residential_listing(
            str(listing.get("description") or ""),
            title=str(listing.get("title") or ""),
        ):
            continue
        if listing.get("is_scam_likely"):
            continue
        if listing.get("price") is not None and not price_within_budget(listing):
            continue
        if is_excluded_location(listing):
            continue
        if is_stale_listing(listing):
            continue
        if queue_excluded_move_in(listing):
            continue
        from lfr.score.listing_rules import listing_is_short_stay

        if listing_is_short_stay(listing):
            continue
        results.append(listing)
    return results


def get_zillow_queue_listings(*, limit: int | None = None) -> list[dict[str, Any]]:
    """All fetched Zillow rows for the queue — keep them even without a parsed price."""
    from lfr.config import SEARCH_CRITERIA

    init_db()
    sql = """
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                l.posted_at, l.rental_address, l.liked, l.first_seen, l.last_seen,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM listings l
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE l.source = 'zillow'
              AND l.id NOT IN (
                  SELECT listing_id FROM applications WHERE status = 'rejected'
              )
            ORDER BY l.last_seen DESC
            """
    params: list[Any] = []
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    from lfr.listings.location import (
        is_excluded_location,
        is_san_francisco_location,
        listing_location_context,
    )

    cap = int(SEARCH_CRITERIA.get("price_match_max") or SEARCH_CRITERIA.get("max_rent") or 1500)
    results: list[dict[str, Any]] = []
    for row in rows:
        listing = dict(row)
        if listing.get("is_scam_likely"):
            continue
        if is_excluded_location(listing):
            continue
        from lfr.score.listing_rules import listing_is_short_stay

        if listing_is_short_stay(listing):
            continue
        ctx = listing_location_context(listing)
        if not is_san_francisco_location(
            primary=ctx["primary"],
            full=ctx["full"],
            rental_location=ctx["rental_location"],
            city=ctx.get("city") or "",
            url=ctx.get("url") or "",
        ):
            continue
        price = listing.get("price")
        if price is not None:
            try:
                if int(price) > cap:
                    continue
            except (TypeError, ValueError):
                pass
        results.append(listing)
    return results


def get_unscored_queue_listings(*, limit: int | None = None) -> list[dict[str, Any]]:
    """Unscored listings for the apply queue (shown as score pending)."""
    from lfr.listings.dates import is_stale_listing
    from lfr.listings.description import is_junk_facebook_title
    from lfr.listings.location import is_excluded_location
    from lfr.pipeline.match import price_within_budget, queue_excluded_move_in
    from lfr.score.listing_rules import _is_non_residential_listing

    init_db()
    sql = """
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                l.posted_at, l.rental_address, l.liked, l.first_seen, l.last_seen,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM listings l
            LEFT JOIN scores s ON l.id = s.listing_id
            WHERE s.listing_id IS NULL
              AND l.id NOT IN (
                  SELECT listing_id FROM applications WHERE status = 'rejected'
              )
            ORDER BY l.last_seen DESC
            """
    params: list[Any] = []
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        listing = dict(row)
        if is_junk_facebook_title(str(listing.get("title") or "")):
            continue
        if _is_non_residential_listing(
            str(listing.get("description") or ""),
            title=str(listing.get("title") or ""),
        ):
            continue
        if not price_within_budget(listing):
            continue
        if is_excluded_location(listing):
            continue
        if is_stale_listing(listing):
            continue
        if queue_excluded_move_in(listing):
            continue
        from lfr.score.listing_rules import listing_is_short_stay

        if listing_is_short_stay(listing):
            continue
        results.append(listing)
    return results


def get_queue_export_listings(*, pool_limit: int | None = None) -> list[dict[str, Any]]:
    """Pool listings plus Facebook card rows and any with queue application rows.

    ``pool_limit=None`` means no artificial cap (preferred).
    """
    # Pool fetch needs a working SQL bound when capped; unlimited uses a high scan ceiling
    # then is filtered in Python (excluded locations already dropped there).
    pool_fetch = pool_limit if pool_limit is not None else 50_000
    pool = get_pool_listings(limit=pool_fetch, exclude_scams=True)
    seen = {row["id"] for row in pool}
    rows = list(pool)
    for row in get_facebook_card_listings(limit=pool_limit):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    for row in get_zillow_queue_listings(limit=pool_limit):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    for row in get_unscored_queue_listings(limit=pool_limit):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    for row in get_listings_with_queue_applications(limit=pool_limit):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    from lfr.listings.location import is_excluded_location

    return [row for row in rows if not is_excluded_location(row)]


