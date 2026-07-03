#!/usr/bin/env python3
"""Hard-filter listings by move-in window and location (no score ranking)."""

from __future__ import annotations

import json
from typing import Any

from config import SEARCH_CRITERIA
from locations import is_excluded_location

MOVE_IN_FITS_OK = frozenset({"ideal"})


def _flags_payload(flags_json: str | None) -> dict[str, Any]:
    if not flags_json:
        return {}
    try:
        parsed = json.loads(flags_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def price_in_focus_band(row: dict[str, Any]) -> bool:
    """True when monthly rent is in the preferred $800–$1000 band."""
    price = row.get("price")
    if price is None:
        return False
    lo = SEARCH_CRITERIA["price_focus_min"]
    hi = SEARCH_CRITERIA["price_focus_max"]
    return lo <= int(price) <= hi


def price_within_budget(row: dict[str, Any]) -> bool:
    """True when rent is at or below match max (default $1300)."""
    price = row.get("price")
    if price is None:
        return False
    cap = SEARCH_CRITERIA.get("price_match_max", SEARCH_CRITERIA["max_rent"])
    return int(price) <= int(cap)


def move_in_fits_window(row: dict[str, Any]) -> bool:
    """True only when move-in is late July 20 – Aug 18, 2026."""
    payload = _flags_payload(row.get("flags_json"))
    fit = str(payload.get("move_in_fit") or "unknown")
    return fit in MOVE_IN_FITS_OK


def listing_matches_criteria(
    row: dict[str, Any],
    *,
    exclude_scams: bool = True,
    exclude_short_term: bool = True,
) -> bool:
    if exclude_scams and row.get("is_scam_likely"):
        return False

    payload = _flags_payload(row.get("flags_json"))
    if exclude_short_term:
        if payload.get("short_term_reject"):
            return False
        rent_period = str(payload.get("rent_period") or "").lower()
        if rent_period in ("weekly", "daily", "sublet"):
            return False

    if not price_within_budget(row):
        return False

    if is_excluded_location(row):
        return False

    if not move_in_fits_window(row):
        return False

    room_flags = payload.get("flags") or []
    if not isinstance(room_flags, list):
        room_flags = [str(room_flags)]
    if "shared_bedroom_reject" in room_flags or "sro_reject" in room_flags:
        return False
    if "office_sublease_reject" in room_flags:
        return False
    if "spanish_listing_reject" in room_flags:
        return False

    return True


def _has_transit_10min_bonus(row: dict[str, Any]) -> bool:
    payload = _flags_payload(row.get("flags_json"))
    flags = payload.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]
    return "transit_10min_bonus" in flags


def sort_matches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """$800–$1000 first, then Muni/Caltrain ≤10 min walk, then up to $1300 by price."""
    lo = SEARCH_CRITERIA["price_focus_min"]
    hi = SEARCH_CRITERIA["price_focus_max"]
    midpoint = (lo + hi) / 2

    def _key(row: dict[str, Any]) -> tuple[int, int, float, int, str]:
        price = int(row.get("price") or 9999)
        in_band = 0 if price_in_focus_band(row) else 1
        transit_bonus = 0 if _has_transit_10min_bonus(row) else 1
        band_distance = abs(price - midpoint) if in_band == 0 else float(price - hi)
        return (in_band, transit_bonus, band_distance, price, row.get("title") or "")

    return sorted(rows, key=_key)