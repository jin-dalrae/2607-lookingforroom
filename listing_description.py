"""Clean listing body text for display (text only, no images)."""

from __future__ import annotations

import re
from typing import Any

from locations import strip_facebook_page_junk

_DISPLAY_LIMIT = 2000
_PREVIEW_LIMIT = 180

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


def needs_description_backfill(row: dict[str, Any]) -> bool:
    """True when a Facebook row still lacks a usable listing description."""
    if str(row.get("source") or "") != "facebook":
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