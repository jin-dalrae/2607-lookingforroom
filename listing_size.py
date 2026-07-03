"""Extract size wording as written in listing posts (not scored flags)."""

from __future__ import annotations

import re
from typing import Any

# Literal phrases from the post — no scoring, no computed totals unless stated.
_SQFT_PHRASE_RE = re.compile(
    r"(\d{1,2}(?:,\d{3})+|\d{2,4})\s*(?:sq\.?\s*ft\.?|sqft|square\s*feet?)",
    re.IGNORECASE,
)
_DIM_SQFT_PHRASE_RE = re.compile(
    r"(\d{1,2}\s*['']?\s*[x×]\s*\d{1,2}\s*['']?\s*(?:sq\.?\s*ft\.?|sqft|square\s*feet?))",
    re.IGNORECASE,
)
_DIM_PHRASE_RE = re.compile(
    r"(\d{1,2}\s*['']?\s*[x×]\s*\d{1,2}\s*['']?(?:\s*(?:ft|feet|foot))?(?!\s*(?:sq\.?\s*ft|sqft|square\s*feet)))",
    re.IGNORECASE,
)
_SIZE_WORD_RE = re.compile(
    r"\b(large room|spacious(?:\s+room|\s+bedroom)?|big bedroom|master bedroom|huge room|generous(?:\s+room|\s+bedroom|\s+space)?)\b",
    re.IGNORECASE,
)


def _listing_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(row.get(key) or "").strip()
        for key in ("title", "description")
        if row.get(key)
    )


def _clean_phrase(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned


def extract_sqft_from_post(row: dict[str, Any]) -> str | None:
    """Return size text exactly as stated in the listing, or None."""
    blob = _listing_text(row)
    if not blob:
        return None

    dim_sqft = _DIM_SQFT_PHRASE_RE.search(blob)
    if dim_sqft:
        return _clean_phrase(dim_sqft.group(1))

    explicit = _SQFT_PHRASE_RE.search(blob)
    if explicit:
        return _clean_phrase(explicit.group(0))

    dim = _DIM_PHRASE_RE.search(blob)
    if dim:
        return _clean_phrase(dim.group(1))

    size_word = _SIZE_WORD_RE.search(blob)
    if size_word:
        return _clean_phrase(size_word.group(1))

    return None


def sqft_sort_value(label: str | None) -> int:
    """Numeric helper for table sort only."""
    if not label:
        return -1
    match = re.search(r"(\d{1,2}(?:,\d{3})+|\d{2,4})", label)
    if match:
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            pass
    return 0