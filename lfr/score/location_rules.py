"""Location tier classification and penalty helpers."""

from __future__ import annotations

from typing import Any

from lfr.config import BUDGET_REALISM, LOCATION_PREFERENCES

from lfr.listings.location import (
    has_sf_primary_signal,
    is_far_east_bay_location,
    mention_place,
    mentions_any_place,
)
from lfr.score.criteria import (
    DALY_CITY_TERMS,
    EAST_BAY_PENALIZE,
    OAKLAND_FAR_TERMS,
    OAKLAND_TERMS,
    SFSU_CLOSE_TERMS,
    _LOCATION_PENALIZE_ORDER,
    _LOCATION_TIER_ORDER,
)


def _mentions_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_sf_proper_listing(text: str) -> bool:
    """True when listing is SF-proper, not Oakland/East Bay/Daly City."""
    if mention_place(text, "south san francisco"):
        return False
    if _is_daly_city(text, text):
        return False
    if _is_oakland(text):
        return False
    if _is_east_bay_penalty(primary=text, full=text):
        return False
    from lfr.score.transit import _is_caltrain_adjacent

    if _is_caltrain_adjacent(text):
        return True
    if "/san-francisco-" in text or "sfc/" in text or "search/sfc" in text:
        return True
    if "san francisco" in text or "city of san francisco" in text:
        return True
    if _mentions_any(text, LOCATION_PREFERENCES["tiers"]["soma_adjacent"]["terms"]):
        return True
    if _mentions_any(text, LOCATION_PREFERENCES["tiers"]["city_center"]["terms"]):
        return True
    if _mentions_any(text, LOCATION_PREFERENCES["tiers"]["central_adjacent"]["terms"]):
        return True
    sf_hood_markers = (
        "russian hill",
        "north beach",
        "castro",
        "mission",
        "hayes",
        "potrero",
        "richmond",
        "sunset",
        "ingleside",
        "excelsior",
        "bayview",
        "west portal",
        "forest hill",
        "noe valley",
        "bernal",
        "dogpatch",
        "china basin",
        "bayshore",
    )
    return _mentions_any(text, sf_hood_markers)


def _location_match(
    terms: tuple[str, ...],
    *,
    neighborhood: str = "",
    title: str = "",
    url: str = "",
    full_text: str = "",
) -> bool:
    """Match location terms in neighborhood/title/url first; full text only as fallback."""
    hood = neighborhood.lower()
    tit = title.lower()
    link = url.lower()
    if hood and _mentions_any(hood, terms):
        return True
    if tit and _mentions_any(tit, terms):
        return True
    if link and _mentions_any(link, terms):
        return True
    return _mentions_any(full_text.lower(), terms)


def _classify_location_tier(
    text: str,
    *,
    neighborhood: str | None = None,
    title: str | None = None,
    url: str | None = None,
) -> tuple[str, int, str | None]:
    """Return (location_tier, score_adjustment, flag)."""
    hood = neighborhood or ""
    tit = title or ""
    link = url or ""
    loc = {
        "neighborhood": hood,
        "title": tit,
        "url": link,
        "full_text": text,
    }

    from lfr.score.transit import _is_caltrain_adjacent

    caltrain_ok = _is_caltrain_adjacent(
        text,
        neighborhood=hood,
        title=tit,
        url=link,
    )

    for tier_name in _LOCATION_PENALIZE_ORDER:
        cfg = LOCATION_PREFERENCES["penalize"][tier_name]
        if _location_match(cfg["terms"], **loc):
            if tier_name == "outer_sf" and caltrain_ok:
                continue
            return tier_name, cfg["penalty"], cfg["flag"]

    if not _is_sf_proper_listing(text):
        if caltrain_ok:
            cfg = LOCATION_PREFERENCES["tiers"]["caltrain_corridor"]
            return "caltrain_corridor", cfg["boost"], cfg["flag"]
        return "none", 0, None

    for tier_name in _LOCATION_TIER_ORDER:
        cfg = LOCATION_PREFERENCES["tiers"][tier_name]
        if _location_match(
            cfg["terms"],
            neighborhood=hood,
            title=tit,
            url=link,
            full_text="",
        ) or _location_match(
            cfg["terms"],
            neighborhood="",
            title="",
            url="",
            full_text=text if tier_name == "soma_adjacent" else "",
        ):
            return tier_name, cfg["boost"], cfg["flag"]

    if caltrain_ok:
        cfg = LOCATION_PREFERENCES["tiers"]["caltrain_corridor"]
        return "caltrain_corridor", cfg["boost"], cfg["flag"]

    return "none", 0, None


def _location_tier_label(tier: str) -> str:
    if tier == "none":
        return ""
    if tier in LOCATION_PREFERENCES["tiers"]:
        return LOCATION_PREFERENCES["tiers"][tier]["digest_label"]
    if tier in LOCATION_PREFERENCES["penalize"]:
        return LOCATION_PREFERENCES["penalize"][tier]["digest_label"]
    return tier

def _is_oakland(text: str) -> bool:
    return mentions_any_place(text, OAKLAND_TERMS)


def _is_sf_richmond(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "richmond district",
            "outer richmond",
            "inner richmond",
            "richmond / seacliff",
            "san francisco",
        )
    )


def _is_east_bay_penalty(*, primary: str, full: str = "", rental_location: str = "") -> bool:
    if is_far_east_bay_location(
        primary=primary,
        full=full,
        rental_location=rental_location,
    ):
        return True
    if _is_oakland(primary):
        return False
    if "richmond" in primary and _is_sf_richmond(primary):
        return False
    if mentions_any_place(primary, EAST_BAY_PENALIZE):
        return True
    if has_sf_primary_signal(primary):
        return False
    if full and full != primary and mentions_any_place(full, EAST_BAY_PENALIZE):
        return True
    return False


def _is_daly_city(primary: str, full: str = "") -> bool:
    if mentions_any_place(primary, DALY_CITY_TERMS):
        return True
    if has_sf_primary_signal(primary):
        return False
    return mentions_any_place(full, DALY_CITY_TERMS) if full else False


def _is_far_oakland(primary: str, full: str = "") -> bool:
    if mentions_any_place(primary, OAKLAND_FAR_TERMS):
        return True
    if has_sf_primary_signal(primary):
        return False
    return mentions_any_place(full, OAKLAND_FAR_TERMS) if full else False


def _is_budget_outer_area(text: str) -> bool:
    return _mentions_any(text, BUDGET_REALISM["areas"])


def _is_normal_outer_rent(price: int | None, text: str) -> bool:
    if price is None:
        return False
    if not _is_budget_outer_area(text):
        return False
    return BUDGET_REALISM["normal_min"] <= price <= BUDGET_REALISM["normal_max"]


def _soften_location_adjustment(adjustment: int, price: int | None, text: str) -> int:
    if adjustment >= 0 or not _is_normal_outer_rent(price, text):
        return adjustment
    return min(0, adjustment + BUDGET_REALISM["penalty_relief"])


def _far_oakland_penalty(price: int | None, text: str) -> int:
    if not _is_far_oakland(text, text):
        return 0
    if _is_normal_outer_rent(price, text):
        return BUDGET_REALISM["far_oakland_penalty"]
    return -25


def _is_sfsu_close_sf(text: str) -> bool:
    """SF-proper proximity to SFSU/CCSF — not Daly City border listings."""
    if _is_daly_city(text, text):
        return False
    if "san francisco" in text or "city of san francisco" in text:
        pass
    elif _is_oakland(text) or _is_east_bay_penalty(primary=text, full=text):
        return False
    if _mentions_any(text, SFSU_CLOSE_TERMS):
        return True
    if "ingleside" in text and "sfsu" in text:
        return True
    return False
