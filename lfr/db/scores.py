"""Listing scores and ranking queries."""

from __future__ import annotations

import json
from typing import Any

from lfr.db.connection import _utcnow, get_connection, init_db
from lfr.db.listings import get_listing_by_id, get_listing_by_url

def get_unscored(limit: int = 20) -> list[dict[str, Any]]:
    """Alias for get_unscored_listings."""
    return get_unscored_listings(limit=limit)


def get_unscored_listings(limit: int = 20) -> list[dict[str, Any]]:
    """Return listings not yet scored by the intelligence layer."""
    from lfr.listings.description import is_queue_scorable

    init_db()
    results: list[dict[str, Any]] = []
    offset = 0
    chunk = max(limit * 4, 80)
    while len(results) < limit:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT l.*
                FROM listings l
                LEFT JOIN scores s ON l.id = s.listing_id
                WHERE s.listing_id IS NULL
                ORDER BY l.last_seen DESC
                LIMIT ? OFFSET ?
                """,
                (chunk, offset),
            ).fetchall()
        if not rows:
            break
        for row in rows:
            listing = dict(row)
            if is_queue_scorable(listing):
                results.append(listing)
                if len(results) >= limit:
                    break
        offset += len(rows)
        if len(rows) < chunk:
            break
    return results[:limit]


def delete_score(listing_id: str) -> bool:
    """Remove a stored score so the listing can be re-tagged."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM scores WHERE listing_id = ?", (listing_id,))
        conn.commit()
    return cur.rowcount > 0


def purge_premature_facebook_scores() -> int:
    """Drop scores for Facebook rows that were tagged before detail fetch."""
    from lfr.listings.description import is_facebook_scoring_ready

    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.id
            FROM listings l
            INNER JOIN scores s ON s.listing_id = l.id
            WHERE l.source = 'facebook'
            """
        ).fetchall()

    purged = 0
    for row in rows:
        listing = get_listing_by_id(str(row["id"]))
        if listing and not is_facebook_scoring_ready(listing):
            if delete_score(listing["id"]):
                purged += 1
    return purged


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

    from lfr.db.applications import update_application_status, upsert_application_draft

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
    """Hard-filter: Aug 1–18, $800–$1000, location rules; sort by price band fit."""
    from lfr.pipeline.match import listing_matches_criteria, sort_matches

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
    from lfr.pipeline.match import _flags_payload, price_within_budget, sort_matches

    init_db()
    scam_clause = "AND s.is_scam_likely = 0" if exclude_scams else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                l.id, l.url, l.title, l.price, l.neighborhood,
                l.description, l.move_in_date, l.source,
                l.posted_at, l.rental_address, l.liked, l.first_seen, l.last_seen,
                s.score, s.is_private_room, s.is_scam_likely,
                s.move_in_compatible, s.flags_json, s.reasoning, s.scored_at
            FROM listings l
            INNER JOIN scores s ON l.id = s.listing_id
            WHERE 1=1 {scam_clause}
              AND l.id NOT IN (
                  SELECT listing_id FROM applications WHERE status = 'rejected'
              )
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
        from lfr.listings.dates import is_stale_listing
        from lfr.listings.location import is_excluded_location

        if is_excluded_location(listing):
            continue
        if is_stale_listing(listing):
            continue
        if "location_reject" in room_flags:
            continue
        if "office_sublease_reject" in room_flags:
            continue
        if "furniture_goods_reject" in room_flags or "non_residential_reject" in room_flags:
            continue
        if "spanish_listing_reject" in room_flags:
            continue
        if "male_household_reject" in room_flags:
            continue
        if "stale_listing_reject" in room_flags:
            continue
        results.append(listing)

    return sort_matches(results)[:limit]


def get_top_listings(limit: int = 15) -> list[dict[str, Any]]:
    """Alias for run.py compatibility."""
    return get_ranked_listings(limit=limit, exclude_scams=True)


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


def mark_listing_scam(listing_id: str) -> None:
    """Mark a listing as likely a scam (score 0, is_scam_likely 1)."""
    init_db()
    with get_connection() as conn:
        existing = conn.execute("SELECT 1 FROM scores WHERE listing_id = ?", (listing_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE scores
                SET score = 0, is_scam_likely = 1, scored_at = ?
                WHERE listing_id = ?
                """,
                (_utcnow(), listing_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO scores
                    (listing_id, score, is_private_room, is_scam_likely,
                     move_in_compatible, flags_json, reasoning, scored_at)
                VALUES (?, 0, 0, 1, 0, '{"flags": ["scam"]}', 'Marked as scam by user', ?)
                """,
                (listing_id, _utcnow()),
            )
        conn.commit()

    from lfr.db.applications import mark_application_rejected
    mark_application_rejected(listing_id, notes="scam")


