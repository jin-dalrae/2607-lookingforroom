"""Local heuristic scorer and flags packing."""

from __future__ import annotations

from typing import Any

from config import LOCATION_PREFERENCES

from lfr.listings.dates import is_stale_listing
from lfr.listings.location import (
    allowed_location_zone,
    is_downtown_oakland_location,
    is_emeryville_location,
    is_excluded_location as _location_hard_exclude,
    is_san_francisco_location,
    is_west_oakland_location,
    listing_location_context,
)
from lfr.score.criteria import CRITERIA, MOVE_IN_FIT_VALUES, SIZE_TIER_VALUES
from lfr.score.listing_rules import (
    _apply_rent_period_scoring,
    _apply_size_scoring,
    _classify_room_type,
    _classify_size,
    _detect_rent_period,
    _effective_monthly_rent,
    _ensure_room_type_flags,
    _has_small_household_signal,
    _is_male_household_listing,
    _is_furniture_or_goods_listing,
    _is_non_residential_listing,
    _is_office_sublease,
    _is_spanish_promoted_listing,
)
from lfr.score.location_rules import (
    _classify_location_tier,
    _far_oakland_penalty,
    _is_daly_city,
    _is_east_bay_penalty,
    _is_far_oakland,
    _is_normal_outer_rent,
    _is_sfsu_close_sf,
    _location_tier_label,
    _soften_location_adjustment,
)
from lfr.score.move_in_scoring import _analyze_move_in, _apply_move_in_scoring
from lfr.score.transit import (
    _classify_transit_tier,
    _muni_caltrain_within_10min,
    _transit_tier_boost,
    _transit_tier_flag,
    _transit_tier_label,
)

def _pack_flags(
    flags: list[str],
    transit_tier: str,
    transit_detail: str | None = None,
    *,
    location_tier: str = "none",
    rent_period: str = "unknown",
    short_term_reject: bool = False,
    sqft: int | None = None,
    size_tier: str = "unknown",
    meets_150_sqft: bool | None = None,
    move_in_signal: str | None = None,
    move_in_fit: str = "unknown",
    landlord_wait_likely: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "flags": flags,
        "transit_tier": transit_tier,
        "location_tier": location_tier,
        "rent_period": rent_period,
        "size_tier": size_tier if size_tier in SIZE_TIER_VALUES else "unknown",
        "move_in_fit": move_in_fit if move_in_fit in MOVE_IN_FIT_VALUES else "unknown",
    }
    if transit_detail:
        payload["transit_detail"] = transit_detail
    if short_term_reject:
        payload["short_term_reject"] = True
        if "short_term_reject" not in flags:
            flags.append("short_term_reject")
    if sqft is not None:
        payload["sqft"] = sqft
    if meets_150_sqft is not None:
        payload["meets_150_sqft"] = meets_150_sqft
    if move_in_signal:
        payload["move_in_signal"] = move_in_signal
    if landlord_wait_likely is not None:
        payload["landlord_wait_likely"] = landlord_wait_likely
    return payload
def _heuristic_score(row: dict[str, Any]) -> dict[str, Any]:
    """Local fallback when Gemini API is unavailable."""
    loc = listing_location_context(row)
    text = loc["full"]
    primary = loc["primary"]
    raw_price = row.get("price")
    price = raw_price if raw_price is not None else 9999
    flags: list[str] = []

    sublease_text = f"{loc['description']} {primary}".strip()
    rent_period, short_term_reject = _detect_rent_period(
        sublease_text or text,
        raw_price,
        title=loc["title"],
    )
    effective_monthly = _effective_monthly_rent(raw_price, rent_period)
    budget_price = effective_monthly if rent_period in ("weekly", "daily") else price

    room_type = _classify_room_type(text)
    flags.append(room_type)

    normal_outer_rent = _is_normal_outer_rent(raw_price, text)
    low_price_scam = (
        not short_term_reject
        and price < 600
        and not normal_outer_rent
    )
    is_scam = (
        low_price_scam
        or "wire transfer" in text
        or "western union" in text
        or room_type in ("shared_bedroom_reject", "sro_reject")
    )
    if is_scam:
        flags.append("scam_signal")

    is_private = room_type in ("private_bedroom", "shared_house_ok")
    small_household = _has_small_household_signal(text)
    if small_household:
        flags.append("small_household")

    move_in_info = _analyze_move_in(text, row.get("move_in_date"))
    move_in_fit = str(move_in_info.get("move_in_fit") or "unknown")
    move_in_ok = move_in_fit == "ideal"

    transit_tier, muni_line = _classify_transit_tier(text)
    transit_bonus = _transit_tier_boost(transit_tier, text) > 0
    transit_adjacent = transit_bonus or transit_tier == "muni_bus"
    tier_flag = _transit_tier_flag(transit_tier)
    if tier_flag:
        flags.append(tier_flag)
    if transit_tier in ("muni_tram", "caltrain") and _muni_caltrain_within_10min(text):
        flags.append("transit_10min_bonus")
    if transit_adjacent:
        flags.append("transit_adjacent")

    if _location_hard_exclude(row):
        flags.append("location_reject")

    zone = allowed_location_zone(row)
    if zone == "san_francisco":
        flags.append("sf_ok")
    elif zone == "west_oakland":
        flags.append("west_oakland_ok")
    elif zone == "downtown_oakland":
        flags.append("downtown_oakland_ok")
    elif zone == "emeryville":
        flags.append("emeryville_ok")
    elif zone == "south_san_francisco":
        flags.append("south_sf_ok")

    if _is_male_household_listing(text, title=loc["title"]):
        flags.append("male_household_reject")

    if is_stale_listing(row):
        flags.append("stale_listing_reject")

    office_sublease = _is_office_sublease(text, title=loc["title"])
    if office_sublease:
        flags.append("office_sublease_reject")
    if _is_furniture_or_goods_listing(text, title=loc["title"]):
        flags.append("furniture_goods_reject")
    if _is_non_residential_listing(text, title=loc["title"]):
        flags.append("non_residential_reject")

    language_text = f"{loc['title']} {loc['description']}".strip()
    if _is_spanish_promoted_listing(language_text, title=loc["title"]):
        flags.append("spanish_listing_reject")

    west_oakland_ok = is_west_oakland_location(
        primary=primary,
        rental_location=loc["rental_location"],
        city=loc["city"],
    )
    if west_oakland_ok:
        flags.append("west_oakland_ok")
    downtown_oakland_ok = is_downtown_oakland_location(
        primary=primary,
        rental_location=loc["rental_location"],
        city=loc["city"],
    )
    if downtown_oakland_ok:
        flags.append("downtown_oakland_ok")
    emeryville_ok = is_emeryville_location(
        primary=primary,
        rental_location=loc["rental_location"],
        city=loc["city"],
    )
    if emeryville_ok:
        flags.append("emeryville_ok")

    east_bay_penalty = _is_east_bay_penalty(
        primary=primary,
        full=text,
        rental_location=loc["rental_location"],
    )
    if east_bay_penalty:
        flags.append("east_bay_penalty")

    daly_city = _is_daly_city(primary, text)
    if daly_city:
        flags.append("daly_city")

    far_oakland = _is_far_oakland(primary, text)
    if far_oakland:
        flags.append("far_oakland")

    sfsu_close = _is_sfsu_close_sf(text)
    if sfsu_close:
        flags.append("sfsu_close")

    location_tier, location_adjust, location_flag = _classify_location_tier(
        text,
        neighborhood=loc["rental_location"] or loc["neighborhood"],
        title=loc["title"],
        url=loc["url"],
    )
    if location_flag:
        flags.append(location_flag)
    if normal_outer_rent:
        flags.append("budget_outer_normal")
        location_adjust = _soften_location_adjustment(location_adjust, raw_price, text)

    score = 50
    if (
        "location_reject" in flags
        or "office_sublease_reject" in flags
        or "furniture_goods_reject" in flags
        or "non_residential_reject" in flags
        or "spanish_listing_reject" in flags
        or "male_household_reject" in flags
        or "stale_listing_reject" in flags
    ):
        score = 5
    elif is_scam and room_type in ("shared_bedroom_reject", "sro_reject"):
        score = 10
    elif is_scam:
        score = 5
    elif room_type == "shared_bedroom_reject":
        score = 15
    elif room_type == "sro_reject":
        score = 10
    else:
        if room_type == "private_bedroom":
            score += 25
        elif room_type == "shared_house_ok":
            score += 20
        if small_household:
            score += 10
        if not short_term_reject and budget_price <= CRITERIA["max_rent"]:
            score += int((CRITERIA["max_rent"] - budget_price) / 50)
        if transit_adjacent:
            score += _transit_tier_boost(transit_tier, text)
        if location_adjust:
            score += location_adjust
        elif sfsu_close:
            score += 5
        if west_oakland_ok and not far_oakland:
            score += 6
        if downtown_oakland_ok and not far_oakland:
            score += 6
        if emeryville_ok:
            score += 4
        if "sf_ok" in flags and transit_tier == "muni_tram" and _muni_caltrain_within_10min(text):
            score += 12
        elif "sf_ok" in flags and transit_tier == "muni_tram":
            score += 6
        elif is_san_francisco_location(
            primary=primary,
            rental_location=loc["rental_location"],
            city=loc["city"],
            url=loc["url"],
        ):
            score += 8
        if east_bay_penalty:
            score -= 25
        score += _far_oakland_penalty(raw_price, text)
        if daly_city:
            score -= 20
            flags.append("daly_city_penalty")

    score = max(0, min(100, score))
    parts = []
    if room_type == "private_bedroom":
        parts.append("private bedroom")
    elif room_type == "shared_house_ok":
        parts.append("small shared house OK")
    elif room_type == "shared_bedroom_reject":
        parts.append("shared bedroom — reject")
    elif room_type == "sro_reject":
        parts.append("SRO/hostel — reject")
    if small_household:
        parts.append("~3-person household")
    if transit_tier in ("muni_tram", "caltrain") and _muni_caltrain_within_10min(text):
        parts.append(f"≤10 min walk to {_transit_tier_label(transit_tier, muni_line)}")
    elif transit_adjacent and transit_tier == "muni_bus":
        parts.append(f"Near {_transit_tier_label(transit_tier, muni_line)}")
    elif transit_tier == "bart":
        parts.append("Near BART (no transit bonus)")
    if location_tier == "outer_sf" and normal_outer_rent:
        parts.append("Excelsior/outer SF — $700–800 is typical rent")
    elif location_tier == "outer_sf" and transit_tier == "caltrain":
        parts.append("outer SF but near Caltrain — OK")
    elif location_tier != "none":
        parts.append(_location_tier_label(location_tier))
    elif sfsu_close:
        parts.append("near SFSU (SF)")
    if west_oakland_ok and not far_oakland:
        parts.append("West Oakland OK")
    if downtown_oakland_ok and not far_oakland:
        parts.append("Downtown Oakland OK")
    if emeryville_ok:
        parts.append("Emeryville OK")
    if "south_sf_ok" in flags and location_tier != "south_san_francisco":
        parts.append("South SF — ~1hr to Market")
    if "male_household_reject" in flags:
        parts.append("male-only household — reject")
    if "stale_listing_reject" in flags:
        parts.append("listed over a week ago — skip")
    if far_oakland:
        if normal_outer_rent:
            parts.append("Oakland east — far but $700–800 is typical")
        else:
            parts.append("far Oakland — likely too far")
    if "office_sublease_reject" in flags:
        parts.append("office/workspace sublease — reject")
    if "spanish_listing_reject" in flags:
        parts.append("Spanish listing — reject")
    if "location_reject" in flags:
        if loc["rental_location"]:
            parts.append(f"too far — {loc['rental_location']}")
        else:
            parts.append("location too far — excluded")
    if east_bay_penalty and "location_reject" not in flags:
        parts.append("East Bay outside Oakland")
    if daly_city:
        parts.append("Daly City — likely too far")
    if is_scam and room_type not in ("shared_bedroom_reject", "sro_reject"):
        parts.append("scam signals")

    score, rent_period, short_term_reject, flags, parts = _apply_rent_period_scoring(
        text=sublease_text or text,
        price=raw_price,
        score=score,
        flags=flags,
        parts=parts,
        title=loc["title"],
        rent_period=rent_period,
        short_term_reject=short_term_reject,
    )

    size_info = _classify_size(text)
    score, size_info, flags, parts = _apply_size_scoring(
        text=text,
        score=score,
        flags=flags,
        parts=parts,
        size_info=size_info,
    )

    score, move_in_info, flags, parts = _apply_move_in_scoring(
        score=score,
        flags=flags,
        parts=parts,
        move_in_info=move_in_info,
    )
    score = max(0, min(100, score))
    reasoning = "; ".join(parts) or "marginal match"

    result = {
        "id": row["id"],
        "score": score,
        "is_private_room": is_private,
        "room_type": room_type,
        "is_scam_likely": is_scam,
        "move_in_compatible": move_in_ok,
        "flags": flags,
        "transit_tier": transit_tier,
        "transit_detail": muni_line,
        "location_tier": location_tier,
        "rent_period": rent_period,
        "short_term_reject": short_term_reject,
        "sqft": size_info.get("sqft"),
        "size_tier": size_info.get("size_tier", "unknown"),
        "meets_150_sqft": size_info.get("meets_150_sqft"),
        "move_in_signal": move_in_info.get("move_in_signal"),
        "move_in_fit": move_in_info.get("move_in_fit", "unknown"),
        "landlord_wait_likely": move_in_info.get("landlord_wait_likely"),
        "reasoning": reasoning[:120],
    }
    _ensure_room_type_flags(result, text)
    return result
