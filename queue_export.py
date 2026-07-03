#!/usr/bin/env python3
"""Export apply-queue JSON for the local / Pages UI."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from apply import load_profile, standard_apply_message
from channels import default_channel_for_listing, is_facebook_listing
from db import (
    get_application_by_listing_id,
    get_queue_export_listings,
    init_db,
)
from listing_dates import (
    format_timestamp_label,
    is_estimated_posted,
    posted_label,
    resolve_posted_at,
)
from map_coords import resolve_listing_coords
from locations import listing_location_context, resolve_display_area, resolve_listing_place
from match import listing_matches_criteria
from listing_move_in import extract_move_in_label
from listing_size import extract_sqft_from_post, sqft_sort_value
from send_mail import extract_listing_email

OUTPUT_PATH = __import__("pathlib").Path(__file__).parent / "site" / "data.json"
EXPORT_LIMIT = 500


def _gmail_compose_url(*, to: str, subject: str, body: str) -> str:
    params = f"view=cm&fs=1&su={quote(subject)}&body={quote(body)}"
    if to:
        params += f"&to={quote(to)}"
    return f"https://mail.google.com/mail/?{params}"


def _flags_list(flags_json: str | None) -> list[str]:
    if not flags_json:
        return []
    try:
        parsed = json.loads(flags_json)
    except (json.JSONDecodeError, TypeError):
        return []
    flags = parsed.get("flags") or []
    return flags if isinstance(flags, list) else [str(flags)]


def _transit_tag(flags_json: str | None, reasoning: str) -> str | None:
    flags = _flags_list(flags_json)
    if "transit_10min_bonus" in flags:
        if "caltrain_adjacent" in flags or "caltrain_corridor" in flags:
            return "≤10 min Caltrain"
        if "muni_tram_adjacent" in flags:
            return "≤10 min Muni"
        return "≤10 min transit"
    if "bart_adjacent" in flags:
        return "BART"
    blob = (reasoning or "").lower()
    if "≤10 min" in blob:
        return blob.split(";")[0].strip()[:40]
    return None


def _queue_status(app_status: str | None) -> str:
    if app_status in (None, "draft"):
        return "to_apply"
    if app_status == "skipped":
        return "skipped"
    if app_status == "replied":
        return "replied"
    if app_status in ("sent", "toured"):
        return "applied"
    return "other"


def _serialize_listing(row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    listing_id = row["id"]
    app = get_application_by_listing_id(listing_id)
    app_status = app["status"] if app else None
    url = row.get("url") or ""
    subject = (profile.get("email_subject") or "Room Rental Inquiry by Aug 18").strip()
    message = standard_apply_message(profile, url)
    to_addr = extract_listing_email(row) or ""
    channel = default_channel_for_listing(row)
    if app and app.get("channel"):
        channel = app["channel"]

    skipped_at = app.get("updated_at") if app and app_status == "skipped" else None
    place = resolve_listing_place(row)
    loc = listing_location_context(row)
    rental_address = place.get("rental_address") or loc.get("rental_location") or ""
    display_neighborhood = resolve_display_area(row)
    sqft_label = extract_sqft_from_post(row)

    posted_at = resolve_posted_at(row)
    posted_estimated = not posted_at or is_estimated_posted(
        {**row, "posted_at": posted_at or row.get("posted_at")}
    )
    scraped_at = row.get("last_seen")
    coords = resolve_listing_coords(
        {
            **row,
            "display_place": display_neighborhood,
            "rental_address": rental_address,
            "city": place.get("city") or "",
        }
    )

    return {
        "id": listing_id,
        "title": row.get("title") or "Untitled",
        "price": row.get("price"),
        "sqftLabel": sqft_label,
        "sqftSort": sqft_sort_value(sqft_label),
        "neighborhood": display_neighborhood,
        "rentalAddress": rental_address,
        "city": place.get("city") or "",
        "state": place.get("state") or "",
        "zip": place.get("zip") or "",
        "url": url,
        "source": row.get("source") or "craigslist",
        "channel": channel,
        "isFacebook": is_facebook_listing(row),
        "isMatch": listing_matches_criteria(row),
        "liked": bool(row.get("liked")),
        "score": row.get("score"),
        "queueStatus": _queue_status(app_status),
        "appStatus": app_status,
        "postedAt": posted_at,
        "postedEstimated": posted_estimated,
        "postedLabel": posted_label(posted_at, estimated=posted_estimated),
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "scrapedAt": scraped_at,
        "scrapedLabel": format_timestamp_label(scraped_at),
        "firstScrapedAt": row.get("first_seen"),
        "skippedAt": skipped_at,
        "skippedLabel": format_timestamp_label(skipped_at) if skipped_at else None,
        "transitTag": _transit_tag(row.get("flags_json"), row.get("reasoning") or ""),
        "moveInLabel": extract_move_in_label(row),
        "to": to_addr,
        "subject": subject,
        "message": message,
        "gmailComposeUrl": _gmail_compose_url(to=to_addr, subject=subject, body=message),
    }


def build_queue_payload(*, export_limit: int = EXPORT_LIMIT) -> dict[str, Any]:
    init_db()
    profile = load_profile()
    subject = (profile.get("email_subject") or "Room Rental Inquiry by Aug 18").strip()

    rows = get_queue_export_listings(pool_limit=export_limit)
    listings = [_serialize_listing(row, profile) for row in rows]
    counts = {
        "toApply": sum(1 for item in listings if item["queueStatus"] == "to_apply"),
        "applied": sum(1 for item in listings if item["queueStatus"] == "applied"),
        "replied": sum(1 for item in listings if item["queueStatus"] == "replied"),
        "skipped": sum(1 for item in listings if item["queueStatus"] == "skipped"),
        "moveInWindow": sum(1 for item in listings if item["isMatch"]),
        "liked": sum(1 for item in listings if item.get("liked")),
        "total": len(listings),
    }

    api_url = os.getenv("APPLY_API_PUBLIC_URL", "").strip().rstrip("/")

    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "apiUrl": api_url,
        "subject": subject,
        "messageTemplate": standard_apply_message(profile, ""),
        "counts": counts,
        "listings": listings,
    }


def write_queue_data(path=None) -> __import__("pathlib").Path:
    from db import backfill_neighborhoods, backfill_posted_at, backfill_rental_addresses

    backfill_rental_addresses()
    backfill_neighborhoods()
    backfill_posted_at(remote_limit=200)
    target = path or OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_queue_payload()
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target