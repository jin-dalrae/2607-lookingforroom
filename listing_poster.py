"""Extract poster / seller names from listing posts."""

from __future__ import annotations

import re
from typing import Any

from locations import strip_facebook_page_junk

_JUNK_NAME_WORDS = frozenset({
    "a",
    "about",
    "and",
    "any",
    "ask",
    "at",
    "available",
    "by",
    "call",
    "contact",
    "details",
    "email",
    "for",
    "if",
    "info",
    "information",
    "interested",
    "looking",
    "me",
    "message",
    "more",
    "number",
    "or",
    "our",
    "seller",
    "show",
    "text",
    "the",
    "this",
    "to",
    "us",
    "via",
    "with",
    "you",
    "your",
})

_FB_SELLER_RE = re.compile(
    r"Seller\s+details\s*\n\s*([^\n]+?)\s*\n\s*Joined\s+Facebook",
    re.IGNORECASE,
)

_CL_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bmy name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bask\s+for\s+([A-Z][a-z]{2,20})\b"),
    re.compile(r"\bcall\s+([A-Z][a-z]{2,20})\b(?=\s+(?:show\s+contact|for\b|at\b))", re.IGNORECASE),
    re.compile(r"\btext\s+([A-Z][a-z]{2,20})\b(?=\s+(?:show\s+contact|for\b|at\b))", re.IGNORECASE),
    re.compile(r"\b(?:llamar a|contactar a)\s+([A-Z][a-z]{2,20})\b", re.IGNORECASE),
)


def _listing_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(row.get(key) or "").strip()
        for key in ("title", "description")
        if row.get(key)
    )


def _clean_name_candidate(raw: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", raw).strip(" .,-")
    if not cleaned or len(cleaned) < 2 or len(cleaned) > 40:
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]+", cleaned):
        return None
    words = [word.lower() for word in cleaned.split()]
    if not words or words[0] in _JUNK_NAME_WORDS:
        return None
    if all(word in _JUNK_NAME_WORDS for word in words):
        return None
    if cleaned.lower().startswith("show contact"):
        return None
    return cleaned


def _extract_facebook_seller_name(text: str) -> str | None:
    match = _FB_SELLER_RE.search(text)
    if not match:
        return None
    return _clean_name_candidate(match.group(1))


def _extract_craigslist_name(text: str) -> str | None:
    for pattern in _CL_NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = _clean_name_candidate(match.group(1))
        if name:
            return name
    return None


def extract_poster_name(row: dict[str, Any]) -> str | None:
    """Return the poster name when it appears in the listing post."""
    description = str(row.get("description") or "")
    title = str(row.get("title") or "")
    source = str(row.get("source") or "")

    blobs = [description, strip_facebook_page_junk(description), _listing_text(row), title]
    seen: set[str] = set()
    for blob in blobs:
        if not blob or blob in seen:
            continue
        seen.add(blob)
        if source == "facebook" or "seller details" in blob.lower():
            name = _extract_facebook_seller_name(blob)
            if name:
                return name
        if source != "facebook":
            name = _extract_craigslist_name(blob)
            if name:
                return name

    if source == "facebook":
        for blob in blobs:
            if blob:
                name = _extract_facebook_seller_name(blob)
                if name:
                    return name

    return None