"""Detect unit beds/baths (1r1b, 2r2b, 3r3b/3r2b, …) from listing text."""

from __future__ import annotations

import re
from typing import Any

_BR_BA_RE = re.compile(
    r"\b(\d)\s*[-/]?\s*(?:br|bd|beds?|bedrooms?)\b"
    r"(?:[^\n]{0,28}?)?"
    r"\b(\d(?:\.5)?)\s*[-/]?\s*(?:ba|baths?|bathrooms?)\b",
    re.IGNORECASE,
)
_BA_BR_RE = re.compile(
    r"\b(\d(?:\.5)?)\s*[-/]?\s*(?:ba|baths?|bathrooms?)\b"
    r"(?:[^\n]{0,28}?)?"
    r"\b(\d)\s*[-/]?\s*(?:br|bd|beds?|bedrooms?)\b",
    re.IGNORECASE,
)
_COMPACT_RB_RE = re.compile(r"\b(\d)\s*r\s*(\d(?:\.5)?)\s*b\b", re.IGNORECASE)
_COMPACT_BB_RE = re.compile(
    r"\b(\d)\s*b(?:ed)?(?:room)?\s*[/x×-]?\s*(\d(?:\.5)?)\s*b(?:ath)?(?:room)?s?\b",
    re.IGNORECASE,
)
_ZILLOW_CARD_RE = re.compile(
    r"(\d+)\s*(?:bds?|beds?|bd|br)\s*[|·,/-]\s*(\d(?:\.5)?)\s*(?:ba|baths?)",
    re.IGNORECASE,
)
_BEDS_ONLY_RE = re.compile(
    r"\b(?:(?P<n>\d)|(?P<w>one|two|three|four|studio))\s*"
    r"(?:br|bd|beds?|bedrooms?)\b",
    re.IGNORECASE,
)
_BATHS_ONLY_RE = re.compile(
    r"\b(?:(?P<n>\d(?:\.5)?)|(?P<w>one|two|three|four))\s*"
    r"(?:ba|baths?|bathrooms?)\b",
    re.IGNORECASE,
)
_STUDIO_RE = re.compile(r"\bstudio\b", re.IGNORECASE)
_PRIVATE_BATH_RE = re.compile(r"\bprivate\s+(?:bath|bathroom|ba)\b", re.IGNORECASE)
_ENSUITE_RE = re.compile(
    r"\b(?:en[- ]?suite|ensuite)\b"
    r"|\bown\s+(?:bath|bathroom|ba)\b"
    r"|\battached\s+(?:bath|bathroom)\b"
    r"|\bprivate\s+(?:full\s+)?(?:bath|bathroom|ba)\b"
    r"|\bbath(?:room)?\s+in\s+(?:the\s+)?(?:room|unit|apartment|bedroom)\b",
    re.IGNORECASE,
)
_SHARED_BATH_RE = re.compile(
    r"\bshared\s+(?:bath|bathroom|ba)\b"
    r"|\bshare\s+(?:a\s+|the\s+)?(?:bath|bathroom)\b"
    r"|\bcommunal\s+(?:bath|bathroom)\b",
    re.IGNORECASE,
)
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "studio": 0}


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _word_or_digit(match: re.Match[str], group_n: str, group_w: str) -> int | None:
    if match.group(group_n):
        return _to_int(match.group(group_n))
    word = (match.group(group_w) or "").lower()
    return _WORD_NUM.get(word)


def detect_layout(
    text: str,
    *,
    beds: int | None = None,
    baths: float | int | None = None,
) -> dict[str, Any]:
    """Return {beds, baths, label} when a layout can be parsed."""
    unit_beds = _to_int(beds)
    unit_baths = _to_int(baths)
    blob = text or ""

    if unit_beds is None or unit_baths is None:
        for pattern, beds_first in (
            (_ZILLOW_CARD_RE, True),
            (_BR_BA_RE, True),
            (_COMPACT_RB_RE, True),
            (_COMPACT_BB_RE, True),
            (_BA_BR_RE, False),
        ):
            match = pattern.search(blob)
            if not match:
                continue
            left = _to_int(match.group(1))
            right = _to_int(match.group(2))
            if beds_first:
                unit_beds = unit_beds if unit_beds is not None else left
                unit_baths = unit_baths if unit_baths is not None else right
            else:
                unit_baths = unit_baths if unit_baths is not None else left
                unit_beds = unit_beds if unit_beds is not None else right
            break

    if unit_beds is None:
        if _STUDIO_RE.search(blob):
            unit_beds = 0
        else:
            beds_match = _BEDS_ONLY_RE.search(blob)
            if beds_match:
                unit_beds = _word_or_digit(beds_match, "n", "w")

    if unit_baths is None:
        baths_match = _BATHS_ONLY_RE.search(blob)
        if baths_match:
            unit_baths = _word_or_digit(baths_match, "n", "w")
        elif _PRIVATE_BATH_RE.search(blob):
            unit_baths = 1

    label = ""
    if unit_beds == 0:
        label = "studio"
    elif unit_beds is not None and unit_baths is not None:
        label = f"{unit_beds}r{unit_baths}b"
    elif unit_beds is not None:
        label = f"{unit_beds}br"
    elif unit_baths is not None:
        label = f"{unit_baths}ba"

    private_bath = bool(_PRIVATE_BATH_RE.search(blob) or _ENSUITE_RE.search(blob))
    return {
        "beds": unit_beds,
        "baths": unit_baths,
        "label": label,
        "private_bath": private_bath,
    }


def bath_privacy(layout: dict[str, Any] | None, text: str = "") -> str:
    """Return 'private', 'shared', or 'unknown' for the renter's bathroom."""
    info = layout or {}
    blob = text or ""
    has_private = bool(info.get("private_bath") or _ENSUITE_RE.search(blob) or _PRIVATE_BATH_RE.search(blob))
    has_shared = bool(_SHARED_BATH_RE.search(blob))
    if has_private:
        return "private"
    if has_shared:
        return "shared"
    beds = info.get("beds")
    baths = info.get("baths")
    if beds == 0 and baths:
        return "private"
    if beds == 1 and baths == 1:
        return "private"
    try:
        bed_n = int(beds) if beds is not None else None
        bath_n = float(baths) if baths is not None else None
    except (TypeError, ValueError):
        bed_n, bath_n = None, None
    if bed_n is not None and bath_n is not None and bed_n >= 2 and bath_n < bed_n:
        return "shared"
    if bed_n is not None and bath_n is not None and bed_n >= 1 and bath_n >= bed_n:
        return "private"
    return "unknown"


def layout_score_adjustment(
    layout: dict[str, Any],
    preferred: list[dict[str, Any]] | None,
    *,
    others_ok: bool = True,
) -> tuple[int, str | None, str | None]:
    """Return (boost, flag, reasoning) for a detected layout vs preferred list."""
    if not preferred:
        return 0, None, None

    beds = layout.get("beds")
    baths = layout.get("baths")
    if beds is None and baths is None:
        return (4, "layout_unspecified", "layout unspecified — still OK") if others_ok else (0, None, None)

    for spec in preferred:
        if not isinstance(spec, dict):
            continue
        want_beds = _to_int(spec.get("beds"))
        want_baths = _to_int(spec.get("baths"))
        if want_beds is None:
            continue
        if beds != want_beds:
            continue
        if want_baths is not None and baths is not None and baths != want_baths:
            continue
        label = str(spec.get("label") or f"{want_beds}r{want_baths or ''}b").strip()
        flag = "layout_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if want_beds == 1 and (want_baths or 1) == 1:
            return 16, flag, f"{label} — preferred whole 1 bed / 1 bath"
        if want_beds == 3:
            return 14, flag, f"{label} — preferred shared house"
        if want_beds == 2:
            return 13, flag, f"{label} — preferred shared house"
        return 10, flag, f"{label} — preferred layout"

    if others_ok:
        label = layout.get("label") or "other layout"
        return 4, "layout_other_ok", f"{label} — other option, still open"
    return 0, None, None
