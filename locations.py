"""Shared location parsing and matching for listings."""

from __future__ import annotations

import re
from typing import Any

from config import LOCATION_EXCLUDE

# Cities too far from SF/Oakland BART corridor — hard reject in matches and pool.
FAR_EAST_BAY_EXCLUDE = (
    "pittsburg",
    "pittsburgh",
    "antioch",
    "vallejo",
    "benicia",
    "fairfield",
    "livermore",
    "brentwood",
    "discovery bay",
    "el sobrante",
    "sobrante",
    "hercules",
    "rodeo",
    "oakley",
    "byron",
    "tracy",
    "stockton",
)

FB_JUNK_MARKERS = (
    "today's picks",
    "todays picks",
    "getting around",
    "provided by walk score",
    "nearby transit",
    "nearby schools",
    "provided by greatschools",
    "you are currently offline",
    "number of unread notifications",
    "browse all",
    "marketplace access",
    "create new listing",
    "buy and sell groups",
    "edit marketplace settings",
)

_RENTAL_LOCATION_RE = re.compile(
    r"rental location\s*\n\s*([^\n]+)",
    re.IGNORECASE,
)
_LISTED_ADDRESS_RE = re.compile(
    r"\n([0-9][^\n]{8,80},\s*(?:ca|california)\b[^\n]*)",
    re.IGNORECASE,
)

_SF_PRIMARY_MARKERS = (
    "san francisco",
    "city of san francisco",
    "/san-francisco-",
    "sfc/",
    "search/sfc",
    "soma",
    "mission",
    "castro",
    "hayes",
    "potrero",
    "embarcadero",
    "financial district",
    "civic center",
    "south beach",
    "mission bay",
    "dogpatch",
    "noe valley",
    "bernal",
    "inner mission",
    "russian hill",
    "north beach",
    "sunset",
    "richmond district",
    "outer richmond",
    "inner richmond",
)


def _compile_place_pattern(term: str) -> re.Pattern[str]:
    cleaned = re.escape(term.strip().lower())
    return re.compile(rf"(?<![a-z0-9]){cleaned}(?![a-z0-9])", re.IGNORECASE)


_PLACE_PATTERNS: dict[str, re.Pattern[str]] = {}


def mention_place(text: str, term: str) -> bool:
    """Word-boundary place match — avoids substring hits inside longer tokens."""
    key = term.strip().lower()
    if not key or not text:
        return False
    pattern = _PLACE_PATTERNS.get(key)
    if pattern is None:
        pattern = _compile_place_pattern(key)
        _PLACE_PATTERNS[key] = pattern
    return bool(pattern.search(text))


def mentions_any_place(text: str, terms: tuple[str, ...]) -> bool:
    return any(mention_place(text, term) for term in terms)


def strip_facebook_page_junk(text: str) -> str:
    """Drop Marketplace chrome and sidebar listings from scraped page text."""
    if not text:
        return ""
    lowered = text.lower()
    cut_at = len(text)
    for marker in FB_JUNK_MARKERS:
        idx = lowered.find(marker)
        if idx != -1:
            cut_at = min(cut_at, idx)
    trimmed = text[:cut_at].strip()
    return trimmed


def extract_rental_location(text: str) -> str:
    """Parse Facebook 'Rental Location' or a street address line when present."""
    if not text:
        return ""
    match = _RENTAL_LOCATION_RE.search(text)
    if match:
        return match.group(1).strip()
    addr = _LISTED_ADDRESS_RE.search(text)
    if addr:
        return addr.group(1).strip()
    return ""


def listing_location_context(row: dict[str, Any]) -> dict[str, str]:
    """Build primary (trusted) and full (fallback) location blobs for a listing."""
    raw_description = str(row.get("description") or "")
    description = strip_facebook_page_junk(raw_description)
    rental_location = extract_rental_location(raw_description) or extract_rental_location(description)
    neighborhood = str(row.get("neighborhood") or "").strip()
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()

    primary_parts = [p for p in (rental_location, neighborhood, title) if p]
    primary = " ".join(primary_parts).lower()
    full = " ".join([primary, description, url]).lower()

    return {
        "primary": primary,
        "full": full,
        "rental_location": rental_location,
        "description": description,
        "neighborhood": neighborhood,
        "title": title,
        "url": url,
    }


def has_sf_primary_signal(primary: str) -> bool:
    if not primary:
        return False
    if mentions_any_place(primary, _SF_PRIMARY_MARKERS):
        return True
    if "richmond" in primary and any(
        phrase in primary
        for phrase in ("richmond district", "outer richmond", "inner richmond", "san francisco")
    ):
        return True
    return False


def is_far_east_bay_location(
    *,
    primary: str = "",
    full: str = "",
    rental_location: str = "",
) -> bool:
    """True when the listing's actual location is far East Bay (e.g. Pittsburg)."""
    checks = [rental_location, primary]
    for blob in checks:
        if blob and mentions_any_place(blob, FAR_EAST_BAY_EXCLUDE):
            return True
    if has_sf_primary_signal(primary):
        return False
    if full and mentions_any_place(full, FAR_EAST_BAY_EXCLUDE):
        return True
    return False


def is_config_excluded_location(row: dict[str, Any]) -> bool:
    """Hard rejects from config (Excelsior, far Oakland, etc.) using primary location first."""
    ctx = listing_location_context(row)
    hood = ctx["neighborhood"].lower()
    primary = ctx["primary"]
    blob = ctx["full"]

    for term in LOCATION_EXCLUDE["terms"]:
        if mention_place(hood, term) or mention_place(primary, term):
            return True
    for term in LOCATION_EXCLUDE.get("blob_terms", ()):
        if mention_place(primary, term):
            return True
        if not has_sf_primary_signal(primary) and mention_place(blob, term):
            return True
    return False


def is_excluded_location(row: dict[str, Any]) -> bool:
    """Any location that should never appear in the apply queue."""
    if is_config_excluded_location(row):
        return True
    ctx = listing_location_context(row)
    return is_far_east_bay_location(
        primary=ctx["primary"],
        full=ctx["full"],
        rental_location=ctx["rental_location"],
    )


def resolve_neighborhood_from_text(
    *,
    title: str = "",
    description: str = "",
    fallback: str = "Facebook Marketplace",
) -> str:
    """Infer a display neighborhood from cleaned listing text."""
    cleaned = strip_facebook_page_junk(description)
    rental = extract_rental_location(description) or extract_rental_location(cleaned)
    if rental:
        city = rental.split(",")[0].strip()
        if city:
            return city
    blob = f"{title} {cleaned}".lower()
    for label in (
        "San Francisco",
        "Oakland",
        "Berkeley",
        "Daly City",
        "El Sobrante",
        "Pittsburg",
        "Antioch",
        "Vallejo",
        "SOMA",
        "Mission",
    ):
        if mention_place(blob, label.lower()):
            return label
    return fallback


def clean_listing_description(description: str | None) -> str | None:
    if not description:
        return None
    cleaned = strip_facebook_page_junk(description)
    return cleaned or None