#!/usr/bin/env python3
"""Export apply-queue JSON for the local / Pages UI."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from apply import load_profile, standard_apply_message
from channels import is_facebook_listing
from db import (
    get_application_by_listing_id,
    get_queue_export_listings,
    init_db,
)
from lfr.listings.dates import (
    format_timestamp_label,
    posted_display_label,
    resolve_posted_at,
)
from lfr.listings.description import queue_display_details, raw_listing_description
from lfr.listings.location import (
    extract_post_display_address,
    listing_location_context,
    resolve_display_area,
    resolve_listing_place,
)
from lfr.listings.move_in import extract_move_in_label, move_in_sort_value
from lfr.listings.poster import extract_poster_name
from lfr.listings.size import extract_sqft_from_post, sqft_sort_value
from lfr.pipeline.match import listing_matches_criteria
from map_coords import resolve_listing_coords
from send_mail import extract_listing_email

OUTPUT_PATH = __import__("pathlib").Path(__file__).resolve().parent.parent.parent / "site" / "data.json"
EXPORT_LIMIT = 500
EXPORT_DESCRIPTION_MAX = 8000
EXPORT_DESCRIPTION_RAW_MAX = 12000


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
    if app_status == "rejected":
        return "gone"
    if app_status in ("sent", "toured"):
        return "applied"
    return "other"


def _serialize_listing(row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    listing_id = row["id"]
    app = get_application_by_listing_id(listing_id)
    app_status = app["status"] if app else None
    url = row.get("url") or ""
    subject = (profile.get("email_subject") or "Room Rental Inquiry by Aug 18").strip()
    to_addr = extract_listing_email(row) or ""
    place = resolve_listing_place(row)
    loc = listing_location_context(row)
    post_address = extract_post_display_address(row)
    rental_address = post_address or place.get("rental_address") or loc.get("rental_location") or ""
    display_neighborhood = post_address or resolve_display_area(row)
    sqft_label = extract_sqft_from_post(row)
    move_in_label = extract_move_in_label(row)
    description_text, details_pending = queue_display_details(row)
    if EXPORT_DESCRIPTION_MAX and len(description_text) > EXPORT_DESCRIPTION_MAX:
        description_text = description_text[: EXPORT_DESCRIPTION_MAX].rstrip()
    details_raw = raw_listing_description(row)
    if EXPORT_DESCRIPTION_RAW_MAX and len(details_raw) > EXPORT_DESCRIPTION_RAW_MAX:
        details_raw = details_raw[: EXPORT_DESCRIPTION_RAW_MAX].rstrip()

    posted_at = resolve_posted_at(row)
    scraped_at = row.get("last_seen")
    coords = resolve_listing_coords(
        {
            **row,
            "display_place": display_neighborhood,
            "rental_address": rental_address,
            "city": place.get("city") or "",
        }
    )

    app_notes = ""
    if app and app.get("notes"):
        raw_notes = app["notes"]
        try:
            parsed = json.loads(raw_notes)
            if isinstance(parsed, dict):
                app_notes = parsed.get("user_notes") or ""
            else:
                app_notes = raw_notes
        except Exception:
            app_notes = raw_notes

    return {
        "id": listing_id,
        "title": row.get("title") or "Untitled",
        "price": row.get("price"),
        "sqftLabel": sqft_label,
        "sqftSort": sqft_sort_value(sqft_label),
        "neighborhood": display_neighborhood,
        "rentalAddress": rental_address,
        "displayAddress": rental_address or display_neighborhood,
        "city": place.get("city") or "",
        "state": place.get("state") or "",
        "zip": place.get("zip") or "",
        "url": url,
        "source": row.get("source") or "craigslist",
        "isFacebook": is_facebook_listing(row),
        "isMatch": listing_matches_criteria(row),
        "liked": bool(row.get("liked")),
        "score": row.get("score"),
        "scorePending": row.get("score") is None,
        "scoreLabel": "Pending"
        if row.get("score") is None
        else str(int(row.get("score"))),
        "appStatus": app_status,
        "queueStatus": _queue_status(app_status),
        "appUpdatedAt": app.get("updated_at") if app else None,
        "appSentAt": app.get("sent_at") if app else None,
        "appRepliedAt": app.get("replied_at") if app else None,
        "appTouredAt": app.get("toured_at") if app else None,
        "appRejectedAt": app.get("rejected_at") if app else None,
        "appSkippedAt": app.get("skipped_at") if app else None,
        "notes": app_notes,
        "postedAt": posted_at,
        "postedLabel": posted_display_label(row),
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "scrapedAt": scraped_at,
        "scrapedLabel": format_timestamp_label(scraped_at),
        "transitTag": _transit_tag(row.get("flags_json"), row.get("reasoning") or ""),
        "moveInLabel": move_in_label,
        "moveInSort": move_in_sort_value(move_in_label),
        "posterName": extract_poster_name(row),
        "details": description_text or None,
        "detailsRaw": details_raw or None,
        "detailsPending": details_pending,
        "to": to_addr,
    }


def _is_specific_street_address(address: str) -> bool:
    if not address:
        return False
    clean = re.sub(r"[^\w\s]", " ", address.lower()).strip()
    generic_words = {
        "san francisco", "sf", "san francisco ca", "sf ca",
        "oakland", "oakland ca", "west oakland", "downtown oakland",
        "emeryville", "emeryville ca", "south san francisco", "south sf",
        "south san francisco ca", "south sf ca", "ssf", "ssf ca",
        "california", "ca", "united states", "usa", "unknown", "unknown area"
    }
    if clean in generic_words:
        return False
    if len(clean) < 10:
        return False
    if not any(char.isdigit() for char in clean):
        if " and " not in clean and " & " not in clean:
            return False
    return True


def _normalize_title_words(title: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    words = {w for w in cleaned.split() if len(w) > 3}
    exclude = {"room", "rent", "private", "bedroom", "apartment", "house", "for rent", "available", "shared"}
    return words - exclude


def _normalize_description_words(desc: str) -> set[str]:
    if not desc:
        return set()
    cleaned = re.sub(r"[^\w\s]", " ", desc.lower())
    words = {w for w in cleaned.split() if len(w) > 4}
    exclude = {
        "room", "rent", "private", "bedroom", "apartment", "house", "available", "shared",
        "kitchen", "bathroom", "utilities", "included", "laundry", "closet"
    }
    return words - exclude


def group_similar_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent = {item["id"]: item["id"] for item in listings}

    def find(i):
        path = []
        while parent[i] != i:
            path.append(i)
            i = parent[i]
        for node in path:
            parent[node] = i
        return i

    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    n = len(listings)
    for i in range(n):
        item_i = listings[i]
        desc_i = (item_i.get("details") or "").strip()
        words_desc_i = _normalize_description_words(desc_i)

        for j in range(i + 1, n):
            item_j = listings[j]
            desc_j = (item_j.get("details") or "").strip()

            is_match = False

            if words_desc_i and len(desc_j) > 40:
                words_desc_j = _normalize_description_words(desc_j)
                shared_desc = words_desc_i & words_desc_j
                if len(shared_desc) >= 12 or (len(shared_desc) / max(len(words_desc_i), len(words_desc_j)) >= 0.6):
                    is_match = True

            if is_match:
                union(item_i["id"], item_j["id"])

    group_map: dict[str, list[dict[str, Any]]] = {}
    for item in listings:
        root_id = find(item["id"])
        item["groupId"] = root_id
        group_map.setdefault(root_id, []).append(item)

    for root_id, members in group_map.items():
        max_score = max((item.get("score") or 0) for item in members)
        min_price = min((item.get("price") or 99999) for item in members)
        is_grouped = len(members) > 1

        for item in members:
            item["groupMaxScore"] = max_score
            item["groupMinPrice"] = min_price
            item["isGrouped"] = is_grouped
            item["duplicateCount"] = len(members) - 1

    return listings


def build_queue_payload(*, export_limit: int = EXPORT_LIMIT) -> dict[str, Any]:
    init_db()
    profile = load_profile()
    subject = (profile.get("email_subject") or "Room Rental Inquiry by Aug 18").strip()

    rows = get_queue_export_listings(pool_limit=export_limit)
    listings = [_serialize_listing(row, profile) for row in rows]
    listings = group_similar_listings(listings)
    counts = {
        "toApply": sum(1 for item in listings if item["queueStatus"] == "to_apply"),
        "applied": sum(1 for item in listings if item["queueStatus"] == "applied"),
        "replied": sum(1 for item in listings if item["queueStatus"] == "replied"),
        "skipped": sum(1 for item in listings if item["queueStatus"] == "skipped"),
        "gone": sum(1 for item in listings if item["queueStatus"] == "gone"),
        "moveInWindow": sum(1 for item in listings if item["isMatch"]),
        "liked": sum(1 for item in listings if item.get("liked")),
        "pendingScore": sum(1 for item in listings if item.get("scorePending")),
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


def write_queue_data(path=None, *, run_backfill: bool = True) -> __import__("pathlib").Path:
    if run_backfill:
        from db import (
            backfill_facebook_details,
            backfill_facebook_junk_titles,
            backfill_move_in_dates,
            backfill_neighborhoods,
            backfill_posted_at,
            backfill_rental_addresses,
            purge_premature_facebook_scores,
        )

        purge_premature_facebook_scores()
        backfill_rental_addresses()
        backfill_move_in_dates()
        backfill_neighborhoods()
        backfill_posted_at(remote_limit=int(os.getenv("POSTED_BACKFILL_LIMIT", "50")))
        title_limit = int(os.getenv("FB_TITLE_BACKFILL_LIMIT", "5"))
        if title_limit > 0:
            backfill_facebook_junk_titles(limit=title_limit)
        detail_limit = int(os.getenv("DETAIL_BACKFILL_LIMIT", "25"))
        detail_rounds = int(os.getenv("DETAIL_BACKFILL_ROUNDS", "3"))
        detail_stats = {"updated": 0, "rescored": 0}
        if detail_limit > 0:
            for _ in range(max(detail_rounds, 1)):
                round_stats = backfill_facebook_details(limit=detail_limit, queue_only=True)
                detail_stats["updated"] += round_stats.get("updated", 0)
                detail_stats["rescored"] += round_stats.get("rescored", 0)
                if not round_stats.get("updated"):
                    break
        import filter as listing_filter

        if detail_stats.get("updated") or detail_stats.get("rescored"):
            listing_filter.run(use_gemini=False)
        score_rounds = int(os.getenv("SCORE_ROUNDS", "25"))
        for _ in range(score_rounds):
            if listing_filter.run(use_gemini=False) == 0:
                break
    target = path or OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_queue_payload()
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target