"""Listing field backfill jobs."""

from __future__ import annotations

from typing import Any

from lfr.db.connection import get_connection, init_db
from lfr.db.listings import get_listing_by_id, upsert_listing
from lfr.db.scores import delete_score

def backfill_rental_addresses(*, limit: int | None = None) -> int:
    """Parse rental_address/neighborhood from stored descriptions. Returns rows updated."""
    from lfr.listings.location import (
        extract_post_display_address,
        is_fb_search_area_label,
        is_junk_location_line,
        resolve_neighborhood_from_text,
    )

    init_db()
    with get_connection() as conn:
        query = """
            SELECT id, title, description, neighborhood, rental_address, source
            FROM listings
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(query, params).fetchall()

    updated = 0
    for row in rows:
        listing = dict(row)
        rental_address = extract_post_display_address(listing).strip()
        existing_address = (listing.get("rental_address") or "").strip()
        existing_hood = (listing.get("neighborhood") or "").strip()
        address_is_junk = is_junk_location_line(existing_address)
        hood_is_junk = is_junk_location_line(existing_hood)

        neighborhood = listing.get("neighborhood") or ""
        hood_low = neighborhood.lower()
        if (
            not neighborhood
            or hood_low.startswith("facebook")
            or "marketplace" in hood_low
            or is_fb_search_area_label(neighborhood)
            or hood_is_junk
        ):
            neighborhood = rental_address or resolve_neighborhood_from_text(
                title=str(listing.get("title") or ""),
                description=str(listing.get("description") or ""),
                fallback=neighborhood if not hood_is_junk else "Unknown",
            )

        if not rental_address and not hood_is_junk and not address_is_junk:
            continue
        if rental_address == existing_address and neighborhood == existing_hood:
            continue

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE listings
                SET rental_address = ?, neighborhood = ?
                WHERE id = ?
                """,
                (rental_address, neighborhood, listing["id"]),
            )
            conn.commit()
        updated += 1
    return updated


def backfill_move_in_dates(*, limit: int | None = None) -> int:
    """Set move_in_date from post text or scrape day for legacy rows."""
    from lfr.listings.move_in import (
        extract_move_in_label,
        resolve_move_in_date_storage,
        should_refresh_move_in_date,
    )

    init_db()
    with get_connection() as conn:
        query = """
            SELECT l.id, l.title, l.description, l.move_in_date,
                   l.first_seen, l.last_seen, s.flags_json
            FROM listings l
            LEFT JOIN scores s ON s.listing_id = l.id
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(query, params).fetchall()

    updated = 0
    for row in rows:
        listing = dict(row)
        if not should_refresh_move_in_date(listing):
            continue
        resolved = resolve_move_in_date_storage(listing)
        if resolved == (listing.get("move_in_date") or ""):
            continue
        with get_connection() as conn:
            conn.execute(
                "UPDATE listings SET move_in_date = ? WHERE id = ?",
                (resolved, listing["id"]),
            )
            conn.commit()
        updated += 1
        listing["move_in_date"] = resolved
        _ = extract_move_in_label(listing)
    return updated


def backfill_neighborhoods(*, limit: int | None = None) -> int:
    """Fix stored neighborhoods that still contain Facebook search chrome."""
    from lfr.listings.location import clean_display_area, resolve_display_area

    init_db()
    with get_connection() as conn:
        query = """
            SELECT id, title, description, neighborhood, rental_address, source, url
            FROM listings
            WHERE lower(neighborhood) LIKE 'facebook%'
               OR lower(neighborhood) LIKE '%marketplace%'
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(query, params).fetchall()

    updated = 0
    for row in rows:
        listing = dict(row)
        new_hood = resolve_display_area(listing)
        cleaned = clean_display_area(new_hood)
        if not cleaned or cleaned.lower() == "unknown":
            continue
        existing = clean_display_area(str(listing.get("neighborhood") or ""))
        if cleaned == existing:
            continue
        with get_connection() as conn:
            conn.execute(
                "UPDATE listings SET neighborhood = ? WHERE id = ?",
                (cleaned, listing["id"]),
            )
            conn.commit()
        updated += 1
    return updated


def backfill_posted_at(
    *,
    limit: int | None = None,
    remote_limit: int = 200,
) -> dict[str, int]:
    """Fill exact posted_at from listing text or Craigslist page datetime."""
    import time

    from lfr.listings.dates import (
        fetch_craigslist_posted_at,
        is_estimated_posted,
        parse_posted_at,
    )

    init_db()
    with get_connection() as conn:
        query = """
            SELECT id, url, title, description, posted_at, first_seen, source
            FROM listings
            WHERE posted_at IS NULL
               OR trim(posted_at) = ''
               OR posted_at = first_seen
            ORDER BY last_seen DESC
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(query, params).fetchall()

    stats = {"parsed": 0, "fetched": 0, "unchanged": 0}
    remote_budget = remote_limit

    for row in rows:
        listing = dict(row)
        if not is_estimated_posted(listing) and listing.get("posted_at"):
            continue

        posted_at = parse_posted_at(
            " ".join(
                str(listing.get(k) or "")
                for k in ("description", "title")
            )
        )
        source = "parsed" if posted_at else ""

        if (
            not posted_at
            and remote_budget > 0
            and str(listing.get("source") or "") == "craigslist"
            and listing.get("url")
        ):
            posted_at = fetch_craigslist_posted_at(listing["url"])
            if posted_at:
                source = "fetched"
                remote_budget -= 1
                time.sleep(0.2)

        if not posted_at:
            stats["unchanged"] += 1
            continue

        stats[source if source in stats else "parsed"] += 1

        with get_connection() as conn:
            conn.execute(
                "UPDATE listings SET posted_at = ? WHERE id = ?",
                (posted_at, listing["id"]),
            )
            conn.commit()

    return stats


def _facebook_incomplete_candidates(*, queue_only: bool) -> list[dict[str, Any]]:
    from lfr.listings.description import needs_facebook_detail_backfill

    if queue_only:
        from lfr.db.queue import get_queue_export_listings

        candidates = get_queue_export_listings()
    else:
        with get_connection() as conn:
            candidates = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM listings
                    WHERE source = 'facebook'
                    ORDER BY last_seen DESC
                    """
                ).fetchall()
            ]
    from lfr.listings.description import queue_display_details

    # Do not re-scrape rows the user already actioned (sent / skipped / gone / etc.)
    skip_statuses = frozenset(
        {"sent", "replied", "toured", "skipped", "rejected", "accepted"}
    )
    with get_connection() as conn:
        actioned = {
            str(row["listing_id"])
            for row in conn.execute(
                f"""
                SELECT listing_id FROM applications
                WHERE status IN ({",".join("?" for _ in skip_statuses)})
                """,
                tuple(skip_statuses),
            ).fetchall()
        }

    needs = [
        row
        for row in candidates
        if needs_facebook_detail_backfill(row)
        and str(row.get("id") or "") not in actioned
    ]
    needs.sort(key=lambda row: (0 if not queue_display_details(row)[0] else 1,))
    return needs


def backfill_facebook_junk_titles(*, limit: int = 5) -> dict[str, int]:
    """Re-fetch Facebook listings stuck with Marketplace chrome titles."""
    if limit <= 0:
        return {"updated": 0, "unchanged": 0, "errors": 0, "total": 0}
    try:
        from lfr.scout.facebook import refetch_junk_titles

        return refetch_junk_titles(limit=limit, headless=True)
    except Exception:
        return {"updated": 0, "unchanged": 0, "errors": 0, "total": 0}


def backfill_facebook_details(
    *,
    limit: int = 25,
    queue_only: bool = True,
) -> dict[str, int]:
    """Fetch Facebook listing pages to fill in text descriptions (no images)."""
    import time

    from lfr.listings.description import is_facebook_scoring_ready

    init_db()
    if limit <= 0:
        return {"fetched": 0, "updated": 0, "unchanged": 0, "errors": 0, "rescored": 0}

    try:
        from lfr.scout.session import session_configured
        from lfr.scout.facebook import DETAIL_DELAY_SEC, _playwright_context, fetch_listing_details
    except ImportError:
        return {"fetched": 0, "updated": 0, "unchanged": 0, "errors": 0, "rescored": 0}

    if not session_configured():
        return {"fetched": 0, "updated": 0, "unchanged": 0, "errors": 0, "rescored": 0}

    needs = _facebook_incomplete_candidates(queue_only=queue_only)[:limit]
    stats = {"fetched": 0, "updated": 0, "unchanged": 0, "errors": 0, "rescored": 0}
    if not needs:
        return stats

    from playwright.sync_api import sync_playwright

    from lfr.scout.facebook import _prepare_detail_page

    with sync_playwright() as playwright:
        browser, context = _playwright_context(playwright, headless=True)
        try:
            page = context.new_page()
            _prepare_detail_page(page)
            for index, listing in enumerate(needs):
                url = str(listing.get("url") or "").strip()
                if not url:
                    continue
                if index > 0:
                    time.sleep(DETAIL_DELAY_SEC)
                print(
                    f"  [{index + 1}/{len(needs)}] {url}",
                    flush=True,
                )
                try:
                    details = fetch_listing_details(page, url)
                    listing_id = str(details["listing_id"])
                    delete_score(listing_id)
                    outcome = upsert_listing(
                        listing_id=listing_id,
                        url=details["url"],
                        title=details["title"],
                        price=details.get("price"),
                        neighborhood=details.get("neighborhood"),
                        description=details.get("description"),
                        move_in_date=details.get("move_in_date"),
                        posted_at=details.get("posted_at"),
                        rental_address=details.get("rental_address"),
                        source="facebook",
                    )
                    stats["fetched"] += 1
                    if outcome == "updated":
                        stats["updated"] += 1
                    else:
                        stats["unchanged"] += 1
                    refreshed = get_listing_by_id(listing_id) or {}
                    if is_facebook_scoring_ready(refreshed):
                        stats["rescored"] += 1
                    desc_len = len(str(details.get("description") or ""))
                    print(f"    → {outcome}, description {desc_len} chars", flush=True)
                except Exception as exc:
                    stats["errors"] += 1
                    print(f"    → error: {exc}", flush=True)
        finally:
            context.close()
            browser.close()

    return stats


