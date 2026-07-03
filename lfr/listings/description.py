"""Clean listing body text for display (text only, no images)."""

from __future__ import annotations

import re
from typing import Any

from lfr.listings.location import strip_facebook_page_junk

_DISPLAY_LIMIT = 2000
_PREVIEW_LIMIT = 180

_JUNK_FB_TITLE_SET = frozenset(
    {
        "notifications",
        "notification",
        "facebook marketplace listing",
    }
)

_MARKETPLACE_TITLE_RE = re.compile(
    r"^\(\d+\)\s*marketplace\s*[-–—]",
    re.IGNORECASE,
)

_JUNK_DESCRIPTION_MARKERS = (
    "marketplace access",
    "edit marketplace settings",
    "browse all",
    "number of unread notifications",
    "create new listing",
    "buy and sell groups",
    "today's picks",
    "getting around",
    "provided by walk score",
)

_FB_CUT_MARKERS = (
    "seller information",
    "send seller a message",
    "report this listing",
    "today's picks",
    "marketplace access",
)

_CL_POSTING_HEADER_RE = re.compile(
    r"^posted:\s*.*?post\s+id:\s*\d+\s*",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def _cut_at_markers(text: str, markers: tuple[str, ...]) -> str:
    low = text.lower()
    cut = len(text)
    for marker in markers:
        idx = low.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    return text[:cut].strip()


def _is_junk_description(text: str) -> bool:
    low = text.lower()
    if len(text.strip()) < 20:
        return True
    if sum(1 for marker in _JUNK_DESCRIPTION_MARKERS if marker in low) >= 2:
        return True
    if low.startswith("marketplace") and "rental location" not in low:
        return True
    return False


def extract_listing_description(row: dict[str, Any]) -> str:
    """Return cleaned post body text for UI display."""
    raw = str(row.get("description") or "").strip()
    if not raw:
        return ""

    source = str(row.get("source") or "")
    if source == "facebook":
        text = _cut_at_markers(raw, _FB_CUT_MARKERS)
        text = strip_facebook_page_junk(text)
        text = _cut_at_markers(text, _FB_CUT_MARKERS)
    else:
        text = _CL_POSTING_HEADER_RE.sub("", raw, count=1).strip()

    text = _normalize_text(text)
    if _is_junk_description(text):
        return ""
    return text[:_DISPLAY_LIMIT]


def description_preview(text: str, *, limit: int = _PREVIEW_LIMIT) -> str:
    cleaned = _normalize_text(text)
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def is_junk_facebook_title(title: str) -> bool:
    """True for Facebook chrome titles that should be re-fetched or hidden."""
    raw = (title or "").strip()
    if not raw:
        return True
    low = raw.lower()
    if low in _JUNK_FB_TITLE_SET:
        return True
    if _MARKETPLACE_TITLE_RE.match(raw):
        return True
    if low.startswith("marketplace") and len(raw) <= 120:
        return True
    return False


def _has_structured_facebook_pdp(row: dict[str, Any]) -> bool:
    """True when detail fetch captured rental location (and optionally availability)."""
    if not (row.get("rental_address") or "").strip():
        return False
    raw_low = str(row.get("description") or "").lower()
    return "rental location" in raw_low or "availability" in raw_low


def needs_description_backfill(row: dict[str, Any]) -> bool:
    """True when a Facebook row still lacks a usable listing description."""
    if str(row.get("source") or "") != "facebook":
        return False
    if _has_structured_facebook_pdp(row):
        return False
    if len(extract_listing_description(row)) >= 40:
        return False
    raw = str(row.get("description") or "").strip()
    if not raw:
        return True
    low = raw.lower()
    if any(marker in low for marker in _JUNK_DESCRIPTION_MARKERS):
        return True
    if "seller details" in low and len(strip_facebook_page_junk(raw)) < 40:
        return True
    return len(raw) < 40


def needs_facebook_detail_backfill(row: dict[str, Any]) -> bool:
    """True when a Facebook row still needs a detail-page fetch (location or body text)."""
    if str(row.get("source") or "") != "facebook":
        return False
    from lfr.listings.location import is_fb_search_area_label

    if _has_structured_facebook_pdp(row):
        hood = (row.get("neighborhood") or "").strip()
        return is_fb_search_area_label(hood)
    if needs_description_backfill(row):
        return True
    if not (row.get("rental_address") or "").strip():
        return True
    hood = (row.get("neighborhood") or "").strip()
    if is_fb_search_area_label(hood):
        return True
    return False


def is_facebook_scoring_ready(row: dict[str, Any]) -> bool:
    """True when a Facebook row has enough detail-page data to tag and score."""
    if str(row.get("source") or "") != "facebook":
        return True
    if needs_facebook_detail_backfill(row):
        return False

    raw = str(row.get("description") or "").strip()
    raw_low = raw.lower()
    has_address = bool((row.get("rental_address") or "").strip())
    if has_address and (
        "rental location" in raw_low
        or "availability" in raw_low
        or len(raw) >= 20
    ):
        return True

    if len(extract_listing_description(row)) >= 40:
        return True
    if len(raw) >= 40:
        return True

    from lfr.listings.move_in import extract_explicit_move_in_label

    if extract_explicit_move_in_label(row):
        return True

    title = str(row.get("title") or "").strip()
    return bool(title and not is_junk_facebook_title(title))


def is_queue_scorable(row: dict[str, Any]) -> bool:
    """True when a listing has enough data for heuristic queue scoring."""
    if is_facebook_scoring_ready(row):
        return True
    if str(row.get("source") or "") != "facebook":
        return bool(str(row.get("title") or "").strip())
    title = str(row.get("title") or "").strip()
    if not title or is_junk_facebook_title(title):
        return False
    price = row.get("price")
    try:
        return price is not None and int(price) > 0
    except (TypeError, ValueError):
        return False