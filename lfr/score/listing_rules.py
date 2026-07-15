"""Rent period, size, room type, and listing rejection helpers."""

from __future__ import annotations

import re
from typing import Any

from lfr.config import BUDGET_REALISM

from lfr.score.criteria import (
    CRITERIA,
    LARGE_SIZE_SIGNALS,
    MIN_ACCEPTABLE_SQFT,
    NICE_TO_HAVE_SQFT,
    FURNITURE_GOODS_TERMS,
    OFFICE_SUBLEASE_TERMS,
    _OFFICE_CONTEXT_RE,
    _ROOM_FOR_RENT_RE,
    RENT_PERIOD_VALUES,
    ROOM_TYPE_VALUES,
    SHARED_BEDROOM_REJECT,
    SHARED_HOUSE_OK_TERMS,
    SMALL_HOUSEHOLD_BOOST,
    SPANISH_RENTAL_TERMS,
    SRO_TERMS,
    MALE_HOUSEHOLD_REJECT,
    _DAILY_RENT_RE,
    _DIMENSION_RE,
    _DIMENSION_SQFT_RE,
    _ENGLISH_ROOM_SIGNALS,
    _LONGER_TERM_OPTION_RE,
    _LONG_TERM_SUBLET_OK_RE,
    _MAX_ROOM_SQFT,
    _MIN_ROOM_SQFT,
    _MONTHLY_RENT_RE,
    _MONTH_SUBLET_TITLE_RE,
    _OFFICE_SUBLEASE_TITLE_RE,
    _RESIDENTIAL_ROOM_RE,
    _SF_OAKLAND_LOW_PRICE_AREAS,
    _SHORT_SUBLEASE_RES,
    _SHORT_TERM_SIGNAL_RE,
    _SPANISH_TITLE_RE,
    _SQFT_EXPLICIT_RE,
    _TITLE_DATE_RANGE_SUBLET_RE,
    _WEEKLY_RENT_RE,
)
from lfr.score.location_rules import _is_oakland, _mentions_any

def _is_sf_oakland_area(text: str) -> bool:
    return _is_oakland(text) or _mentions_any(text, _SF_OAKLAND_LOW_PRICE_AREAS)


def _is_short_sublease(text: str, *, title: str = "") -> bool:
    """Reject temporary residential sublets — not long-term room rentals."""
    tit = (title or "").strip()
    blob = f"{tit} {text}".strip()
    if not blob:
        return False

    if _MONTH_SUBLET_TITLE_RE.search(tit):
        return True
    if _TITLE_DATE_RANGE_SUBLET_RE.search(tit):
        return True
    for pattern in _SHORT_SUBLEASE_RES:
        if pattern.search(blob):
            return True
    if _SHORT_TERM_SIGNAL_RE.search(blob):
        return True

    if _LONG_TERM_SUBLET_OK_RE.search(blob):
        return False

    if _LONGER_TERM_OPTION_RE.search(blob):
        return False

    return False


def _detect_rent_period(
    text: str,
    price: int | None,
    *,
    title: str = "",
) -> tuple[str, bool]:
    """Return (rent_period, short_term_reject).

    short_term_reject is True when the listing should be excluded from monthly rankings.
    """
    if _MONTHLY_RENT_RE.search(text):
        return "monthly", False
    if _WEEKLY_RENT_RE.search(text):
        return "weekly", True
    if _DAILY_RENT_RE.search(text):
        return "daily", True
    if _is_short_sublease(text, title=title):
        return "sublet", True

    short_term_signal = bool(_SHORT_TERM_SIGNAL_RE.search(text))
    in_sf_oakland = _is_sf_oakland_area(text)
    numeric_price = price if price is not None else 9999

    if short_term_signal and numeric_price < CRITERIA["max_rent"]:
        return "weekly", True

    if in_sf_oakland and numeric_price < 400:
        return "daily", True

    return "unknown", False


def _effective_monthly_rent(price: int | None, rent_period: str) -> int | None:
    if price is None:
        return None
    if rent_period == "weekly":
        return int(price * 4.33)
    if rent_period == "daily":
        return price * 30
    return price


def _rent_period_label(rent_period: str) -> str:
    labels = {
        "monthly": "monthly",
        "weekly": "weekly",
        "daily": "daily/nightly",
        "unknown": "unknown",
    }
    return labels.get(rent_period, rent_period)


def _normalize_sqft_value(raw: str) -> int | None:
    try:
        value = int(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if _MIN_ROOM_SQFT <= value <= _MAX_ROOM_SQFT:
        return value
    return None


def _dimension_product(width: int, length: int) -> int | None:
    if 4 <= width <= 30 and 4 <= length <= 30:
        product = width * length
        if _MIN_ROOM_SQFT <= product <= _MAX_ROOM_SQFT:
            return product
    return None


def _parse_sqft(text: str) -> int | None:
    """Extract explicit square footage or compute from dimension pairs (e.g. 10x15)."""
    dim_sqft = _DIMENSION_SQFT_RE.search(text)
    if dim_sqft:
        product = _dimension_product(int(dim_sqft.group(1)), int(dim_sqft.group(2)))
        if product is not None:
            return product

    for dim_match in _DIMENSION_RE.finditer(text):
        product = _dimension_product(int(dim_match.group(1)), int(dim_match.group(2)))
        if product is not None:
            return product

    match = _SQFT_EXPLICIT_RE.search(text)
    if match:
        return _normalize_sqft_value(match.group(1))

    return None


def _has_large_size_signal(text: str) -> bool:
    return _mentions_any(text, LARGE_SIZE_SIGNALS)


def _classify_size(text: str) -> dict[str, Any]:
    """Return sqft, size_tier, and meets_150_sqft for flags_json."""
    sqft = _parse_sqft(text)
    has_large = _has_large_size_signal(text)

    if sqft is not None:
        if sqft >= NICE_TO_HAVE_SQFT:
            size_tier = "large" if (has_large or sqft >= 200) else "ok"
            meets_150_sqft = True
        elif sqft < MIN_ACCEPTABLE_SQFT:
            size_tier = "small"
            meets_150_sqft = False
        else:
            size_tier = "ok"
            meets_150_sqft = False
    elif has_large:
        size_tier = "large"
        meets_150_sqft = None
    else:
        size_tier = "unknown"
        meets_150_sqft = None

    return {
        "sqft": sqft,
        "size_tier": size_tier,
        "meets_150_sqft": meets_150_sqft,
    }


def _apply_size_scoring(
    *,
    text: str,
    score: int,
    flags: list[str],
    parts: list[str],
    size_info: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], list[str], list[str]]:
    """Adjust score/reasoning for room size; returns updated score, size_info, flags, parts."""
    info = size_info or _classify_size(text)
    sqft = info.get("sqft")
    size_tier = str(info.get("size_tier") or "unknown")

    if sqft is not None:
        if sqft >= NICE_TO_HAVE_SQFT:
            score += 5
            flags.append("meets_150_sqft")
            parts.append(f"~{sqft} sqft")
        elif sqft < MIN_ACCEPTABLE_SQFT:
            score = min(score, 40)
            score -= 20
            flags.append("tiny_room")
            parts.append(f"very small ~{sqft} sqft")
        else:
            parts.append(f"~{sqft} sqft")
    elif size_tier == "large":
        score += 5
        flags.append("large_room_signal")
        parts.append("spacious/large room")

    return score, info, flags, parts


def _has_english_room_listing(blob: str) -> bool:
    lowered = blob.lower()
    return any(signal in lowered for signal in _ENGLISH_ROOM_SIGNALS)


def _spanish_before_english(title: str) -> bool:
    """True when Spanish rental wording appears before English in the title."""
    lowered = title.lower()
    english_idx = min(
        (lowered.find(signal) for signal in _ENGLISH_ROOM_SIGNALS if signal in lowered),
        default=len(lowered),
    )
    spanish_markers = (
        "se renta",
        "habitaci",
        "cuarto para rentar",
        "cuarto de renta",
        "para rentar",
        "busco ",
        "renta cuarto",
    )
    spanish_idx = min(
        (lowered.find(marker) for marker in spanish_markers if marker in lowered),
        default=len(lowered),
    )
    return spanish_idx < english_idx


def _is_spanish_promoted_listing(text: str, *, title: str = "") -> bool:
    """Reject listings advertised primarily in Spanish."""
    tit = (title or "").strip()
    blob = f"{tit} {text}".strip()
    if not blob:
        return False

    if _SPANISH_TITLE_RE.search(tit):
        return True
    if _spanish_before_english(tit):
        return True

    if _has_english_room_listing(tit):
        return False

    lowered = blob.lower()
    spanish_hits = sum(1 for term in SPANISH_RENTAL_TERMS if term in lowered)
    if spanish_hits >= 2:
        return True
    if spanish_hits >= 1 and not _has_english_room_listing(blob[:400]):
        return True

    return False


def _is_office_sublease(text: str, *, title: str = "") -> bool:
    """Reject commercial office/workspace subleases — not residential rooms."""
    tit = (title or "").strip().lower()
    blob = f"{tit} {text}".lower()

    if _mentions_any(blob, OFFICE_SUBLEASE_TERMS):
        return True
    if _OFFICE_SUBLEASE_TITLE_RE.search(tit):
        return True
    if _OFFICE_CONTEXT_RE.search(blob):
        return True
    if "office" in tit and not _RESIDENTIAL_ROOM_RE.search(tit):
        return True
    if "office space" in tit and not _RESIDENTIAL_ROOM_RE.search(tit):
        return True
    return False


def _is_furniture_or_goods_listing(text: str, *, title: str = "") -> bool:
    """Reject furniture and household goods posts mistaken for room rentals."""
    tit = (title or "").strip().lower()
    blob = f"{tit} {text}".lower()
    if _ROOM_FOR_RENT_RE.search(blob):
        return False
    if _mentions_any(blob, FURNITURE_GOODS_TERMS):
        return True
    if re.search(r"\b(?:sofa|couch|rug|desk)\b", blob) and "room" not in blob:
        return True
    return False


def _is_non_residential_listing(text: str, *, title: str = "") -> bool:
    return _is_office_sublease(text, title=title) or _is_furniture_or_goods_listing(
        text, title=title
    )


def _has_shared_bedroom_signal(text: str) -> bool:
    if "shared room in" in text or "room in shared" in text:
        return False
    if "private room" in text or "private bedroom" in text:
        bedroom_terms = (
            "shared bed",
            "shared bedroom",
            "share a room",
            "sharing a room",
            "couple",
            "two people in",
            "double occupancy",
            "bunk bed",
        )
        return _mentions_any(text, bedroom_terms)
    return _mentions_any(text, SHARED_BEDROOM_REJECT)


def _is_male_household_listing(text: str, *, title: str = "") -> bool:
    """Reject male-only / men-only roommate households."""
    blob = f"{title} {text}".strip().lower()
    if not blob:
        return False
    if _mentions_any(blob, MALE_HOUSEHOLD_REJECT):
        return True
    if re.search(r"\bmale\s+only\b", blob):
        return True
    if re.search(r"\bmen\s+only\b", blob):
        return True
    return False


def _has_sro_signal(text: str) -> bool:
    if "not sro" in text or "no sro" in text:
        return False
    return _mentions_any(text, SRO_TERMS)


def _has_private_bedroom_signal(text: str) -> bool:
    if _has_shared_bedroom_signal(text):
        return False
    if _OFFICE_CONTEXT_RE.search(text):
        return False
    if "private office" in text or "professional office" in text:
        return False
    return any(
        phrase in text
        for phrase in (
            "private room",
            "private bedroom",
            "own bedroom",
            "own room",
            "your own room",
            "your own bedroom",
        )
    )


def _has_small_household_signal(text: str) -> bool:
    return _mentions_any(text, SMALL_HOUSEHOLD_BOOST)


def _classify_room_type(text: str) -> str:
    """Classify listing into one of the room_type flag values."""
    if _has_sro_signal(text):
        return "sro_reject"
    if _has_shared_bedroom_signal(text):
        return "shared_bedroom_reject"
    if _has_private_bedroom_signal(text) and _mentions_any(text, SHARED_HOUSE_OK_TERMS):
        return "shared_house_ok"
    if _has_private_bedroom_signal(text):
        return "private_bedroom"
    if _mentions_any(text, SHARED_HOUSE_OK_TERMS):
        return "shared_house_ok"
    if "private" in text:
        return "private_bedroom"
    return "shared_house_ok"


def _ensure_room_type_flags(item: dict[str, Any], text: str = "") -> None:
    """Normalize room_type on result and mirror it into flags."""
    room_type = item.get("room_type")
    if room_type not in ROOM_TYPE_VALUES and text:
        room_type = _classify_room_type(text)
    elif room_type not in ROOM_TYPE_VALUES:
        room_type = "shared_house_ok"

    item["room_type"] = room_type
    flags = item.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]
    flags = [f for f in flags if f not in ROOM_TYPE_VALUES]
    flags.append(room_type)
    item["flags"] = flags
    item["is_private_room"] = room_type in ("private_bedroom", "shared_house_ok")


def _apply_rent_period_scoring(
    *,
    text: str,
    price: int | None,
    score: int,
    flags: list[str],
    parts: list[str],
    title: str = "",
    rent_period: str | None = None,
    short_term_reject: bool | None = None,
) -> tuple[int, str, bool, list[str], list[str]]:
    """Adjust score/reasoning for rent period; returns updated score, period, reject, flags, parts."""
    if rent_period is None or short_term_reject is None:
        detected_period, detected_reject = _detect_rent_period(text, price, title=title)
        if rent_period is None:
            rent_period = detected_period
        if short_term_reject is None:
            short_term_reject = detected_reject
    effective_monthly = _effective_monthly_rent(price, rent_period)

    if short_term_reject:
        flags.append("short_term_reject")
        score = min(score, 30)
        parts = [
            p for p in parts
            if "within budget" not in p.lower()
        ]
        if rent_period == "sublet":
            parts.append("short sublease — reject")
        elif rent_period == "weekly" and effective_monthly is not None:
            parts.append(f"weekly ${price} (~${effective_monthly}/mo) — short-term reject")
        elif rent_period == "daily" and effective_monthly is not None:
            parts.append(f"daily ${price} (~${effective_monthly}/mo) — short-term reject")
        else:
            parts.append("short-term/sublet — reject")
    elif rent_period == "monthly":
        parts.append("monthly rent")
        if price is not None and price <= CRITERIA["max_rent"]:
            parts.append(f"${price} within budget")
    elif price is not None and price <= CRITERIA["max_rent"]:
        parts.append(f"${price} within budget")

    return score, rent_period, short_term_reject, flags, parts
