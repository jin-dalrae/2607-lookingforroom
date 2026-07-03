#!/usr/bin/env python3
"""Gemini-powered batch scorer for room listings."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from typing import Any

from locations import (
    has_sf_primary_signal,
    is_excluded_location as _location_hard_exclude,
    is_far_east_bay_location,
    listing_location_context,
    mentions_any_place,
)
from config import (
    AI_MODEL,
    BUDGET_REALISM,
    GCP_KEY,
    GENERATIVE_LANGUAGE_API_KEY,
    LOCATION_PREFERENCES,
    MOVE_IN_SCORING,
    SEARCH_CRITERIA,
    TRANSIT_PREFERENCES,
)
from db import (
    count_listings,
    get_all_listings,
    get_unscored_listings,
    init_db,
    save_score,
    seed_test_listings,
)

# --- User criteria (hardcoded config) ---
MIN_ACCEPTABLE_SQFT = SEARCH_CRITERIA["min_acceptable_sqft"]
NICE_TO_HAVE_SQFT = SEARCH_CRITERIA["nice_to_have_sqft"]
MOVE_IN_TARGET_START: date = SEARCH_CRITERIA["move_in_start"]
MOVE_IN_TARGET_END: date = SEARCH_CRITERIA["move_in_end"]
MOVE_IN_FLEX_WEEKS: int = SEARCH_CRITERIA["move_in_flex_weeks"]
MOVE_IN_WINDOW_START = MOVE_IN_TARGET_START - timedelta(weeks=MOVE_IN_FLEX_WEEKS)
MOVE_IN_WINDOW_END = MOVE_IN_TARGET_END + timedelta(weeks=MOVE_IN_FLEX_WEEKS)
MOVE_IN_REFERENCE_TODAY = date(2026, 7, 2)
MOVE_IN_FIT_VALUES = ("ideal", "maybe", "risky", "too_early", "too_late", "unknown")

CRITERIA = {
    "max_rent": 1300,
    "min_acceptable_sqft": MIN_ACCEPTABLE_SQFT,
    "nice_to_have_sqft": NICE_TO_HAVE_SQFT,
    "move_in_target": "2026-07-20 to 2026-08-18 (late July through Aug 18)",
    "price_focus": "$800–$1000/month",
    "move_in_flex_weeks": 0,
    "wants": (
        "private bedroom in SF or Oakland; also OK as 1 of ~3 people in a small "
        "shared house (~2 other roommates). Prefer private bedroom in a 3-person "
        "household but not required."
    ),
    "location": (
        "SF city center preferred (currently in SOMA): SOMA, South Beach, Mission Bay, "
        "Financial District, Civic Center, Hayes Valley, Inner Mission, Potrero, downtown, "
        "Embarcadero. Homes near Caltrain stations work too (4th & King, Bayshore, Peninsula). "
        "Oakland near BART OK. Outer Sunset/Parkside/Ingleside too far unless Caltrain-adjacent."
    ),
    "current_location": SEARCH_CRITERIA.get("current_location", "SOMA"),
    "transit_priority": (
        "Score bonus ONLY for Muni Metro/tram or Caltrain within ~10 min walk — "
        "NOT BART. Tag bart_adjacent for info but no score boost. "
        "Generic Muni bus is weaker."
    ),
    "accept": [
        "private room / private bedroom",
        "own bedroom in shared house (shared kitchen/bath OK)",
        "small household (~3 people total, ~2 other roommates)",
    ],
    "reject": [
        "obvious scams (price <600 in trendy areas)",
        "wire transfer / Western Union language",
        "shared bedroom (two people in same room)",
        "shared room / couple room / double occupancy",
        "SRO / hostel / single room occupancy",
        "curtain or partition 'rooms'",
        "Berkeley and East Bay outside Oakland",
        "Daly City unless BART-adjacent",
    ],
    "room_type_flags": [
        "private_bedroom",
        "shared_house_ok",
        "shared_bedroom_reject",
        "sro_reject",
    ],
}

BATCH_SIZE = 20
MODEL_FALLBACKS = [
    AI_MODEL.strip("'\""),
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

_MUNI_TRAM_CFG = TRANSIT_PREFERENCES["tiers"]["muni_tram"]
_CALTRAIN_TERMS = TRANSIT_PREFERENCES["tiers"]["caltrain"]["terms"]
_BART_TERMS = TRANSIT_PREFERENCES["tiers"]["bart"]["terms"]
_MUNI_BUS_TERMS = TRANSIT_PREFERENCES["tiers"]["muni_bus"]["terms"]

TRANSIT_TERMS = (
    _MUNI_TRAM_CFG["keywords"]
    + _MUNI_TRAM_CFG["stations"]
    + _CALTRAIN_TERMS
    + _BART_TERMS
    + _MUNI_BUS_TERMS
    + ("muni", "transit", "near station", "walk to muni", "blocks from muni")
)

OAKLAND_TERMS = (
    "oakland",
    "rockridge",
    "macarthur",
    "lake merritt",
    "west oakland",
    "fruitvale",
    "temescal",
    "jack london",
    "uptown oakland",
    "downtown oakland",
    "adams point",
    "grand lake",
)

_LOCATION_TIER_ORDER = tuple(LOCATION_PREFERENCES["tiers"].keys())
_LOCATION_PENALIZE_ORDER = tuple(LOCATION_PREFERENCES["penalize"].keys())

EAST_BAY_PENALIZE = (
    "berkeley",
    "albany",
    "el cerrito",
    "richmond",
    "concord",
    "walnut creek",
    "hayward",
    "fremont",
    "san leandro",
    "alameda",
    "emeryville",
    "pinole",
    "antioch",
    "pleasant hill",
    "lafayette",
    "orinda",
    "martinez",
    "pittsburg",
    "dublin",
    "pleasanton",
    "union city",
    "newark",
    "castro valley",
)

DALY_CITY_TERMS = ("daly city", "daly-city", "colma", "south san francisco", "ssf")

OAKLAND_FAR_TERMS = (
    "oakland east",
    "east oakland",
    "near oakland zoo",
    "near san leandro",
    "san leandro",
)

SFSU_CLOSE_TERMS = (
    "walk to sfsu",
    "walking distance to sfsu",
    "walking distance to sf state",
    "10 min walk to sfsu",
    "minutes walk to sfsu",
    "min walk to sfsu",
    "near sfsu",
    "near sf state",
    "near ccsf",
    "holloway",
    "ocean avenue",
    "balboa park",
    "balboa bart",
    "excelsior / outer mission",
    "parkside",
    "inner sunset",
)

SHARED_BEDROOM_REJECT = (
    "shared bed",
    "shared bedroom",
    "share a room",
    "sharing a room",
    "shared room",
    "couple",
    "two people in",
    "double occupancy",
    "partition room",
    "curtain room",
    "curtain divider",
    "room divider",
    "bunk bed",
    "hostel",
    "dormitory",
    "dorm room",
)

SRO_TERMS = (
    "sro",
    "single room occupancy",
)

OFFICE_SUBLEASE_TERMS = (
    "office sublease",
    "office sublet",
    "sublease office",
    "sublet office",
    "commercial office",
    "office space sublease",
    "office space sublet",
    "coworking",
    "co-working",
    "co working space",
    "shared workspace",
    "shared office space",
    "workspace sublease",
    "workspace sublet",
    "desk rental",
    "desk space for rent",
)

_OFFICE_SUBLEASE_TITLE_RE = re.compile(
    r"office\s+(?:sublease|sublet)\b",
    re.IGNORECASE,
)
_RESIDENTIAL_ROOM_RE = re.compile(
    r"\b(?:private\s+)?(?:room|bedroom|bed)\b",
    re.IGNORECASE,
)

SPANISH_RENTAL_TERMS = (
    "habitación",
    "habitacion",
    "habitaciones",
    "cuarto para rentar",
    "cuarto de renta",
    "cuarto disponible",
    "cuarto en renta",
    "se renta cuarto",
    "se renta",
    "para rentar",
    "renta cuarto",
    "departamento",
    "alquiler",
    "persona sola",
    "sin vicios",
    "casa familiar",
    "cuarto amueblado",
    "se busca",
    "busco ",
)

_ENGLISH_ROOM_SIGNALS = (
    "private room",
    "room for rent",
    "bedroom",
    "looking for",
    "room available",
    "for rent",
    "shared house",
    "shared room",
    "sublet",
    "sublease",
    "move-in",
    "monthly rent",
)

_SPANISH_TITLE_RE = re.compile(
    r"(?:\b\d+\s+habitaci[oó]n|\bse\s+renta\b|\bcuarto\s+(?:para|de|en)\s+renta)",
    re.IGNORECASE,
)

SHARED_HOUSE_OK_TERMS = (
    "shared kitchen",
    "shared bath",
    "shared bathroom",
    "shared living",
    "shared house",
    "shared home",
    "housemates",
    "roommates",
    "2 roommates",
    "two roommates",
    "3 bedroom",
    "3br",
    "3 br",
    "3-bedroom",
    "3-person",
    "3 person",
    "three person",
    "small house",
    "household of 3",
    "household of three",
)

SMALL_HOUSEHOLD_BOOST = (
    "3 bedroom",
    "3br",
    "3 br",
    "3-bedroom",
    "2 roommates",
    "two roommates",
    "2 other roommate",
    "3 person",
    "3-person",
    "three person",
    "small house",
    "household of 3",
    "household of three",
    "3br flat",
    "3br house",
)

ROOM_TYPE_VALUES = (
    "private_bedroom",
    "shared_house_ok",
    "shared_bedroom_reject",
    "sro_reject",
)

RENT_PERIOD_VALUES = ("monthly", "weekly", "daily", "sublet", "unknown")

_WEEKLY_RENT_RE = re.compile(
    r"(?:"
    r"\$\d+\s*/\s*(?:week|wk)\b"
    r"|per\s+week\b"
    r"|/\s*week\b"
    r"|/\s*wk\b"
    r"|\bweekly\b"
    r"|\ba\s+week\b"
    r"|per\s+wk\b"
    r"|\b\d+\s*(?:/|per)\s*wk\b"
    r")",
    re.IGNORECASE,
)

_DAILY_RENT_RE = re.compile(
    r"(?:"
    r"\$\d+\s*/\s*(?:day|night)\b"
    r"|per\s+(?:day|night)\b"
    r"|/\s*(?:day|night)\b"
    r"|\bnightly\b"
    r"|\bdaily\b"
    r"|\bairbnb\b"
    r")",
    re.IGNORECASE,
)

_MONTHLY_RENT_RE = re.compile(
    r"(?:"
    r"per\s+month\b"
    r"|/\s*month\b"
    r"|/\s*mo\b"
    r"|\bmonthly\b"
    r"|per\s+mo\b"
    r"|\ba\s+month\b"
    r"|\$\d+\s*/\s*mo\b"
    r")",
    re.IGNORECASE,
)

_SHORT_TERM_SIGNAL_RE = re.compile(
    r"(?:short[- ]?term\s+sub(?:let|lease)|temporary\s+sub(?:let|lease)|vacation\s+rental|"
    r"sub(?:let|lease)\s+for\s+\d+\s+(?:day|days|week|weeks))",
    re.IGNORECASE,
)

_LONGER_TERM_OPTION_RE = re.compile(
    r"(?:\b(?:3|6|9|12)\s*[- ]?month\s+minimum\b|\bone\s+year\b|\b1[- ]?year\b|\b9[- ]?month\b)",
    re.IGNORECASE,
)

_LONG_TERM_SUBLET_OK_RE = re.compile(
    r"long[- ]?term\s+sub(?:let|lease)",
    re.IGNORECASE,
)

_MONTH_SUBLET_TITLE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+sub(?:let|lease)\b",
    re.IGNORECASE,
)

_TITLE_DATE_RANGE_SUBLET_RE = re.compile(
    r"sub(?:let|lease)\s+\d{1,2}/\d{1,2}\s*[-–]\s*\d{1,2}/\d{1,2}",
    re.IGNORECASE,
)

_SHORT_SUBLEASE_RES = (
    re.compile(
        r"subleas(?:e|ing)\s+(?:my\s+)?(?:room|bedroom|place|apartment|unit)\s+for\s+"
        r"(?:a\s+)?couple\s+(?:of\s+)?weeks",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{1,3}\s+nights?\b", re.IGNORECASE),
    re.compile(r"flat\s+for\s+the\s+stay", re.IGNORECASE),
    re.compile(r"\bfor\s+the\s+stay\b", re.IGNORECASE),
    re.compile(r"while\s+i['']?m\s+away", re.IGNORECASE),
    re.compile(
        r"dates?:\s*.{0,80}?\bto\b",
        re.IGNORECASE,
    ),
    re.compile(r"vacation\s+sub(?:let|lease)", re.IGNORECASE),
)

_MIN_ROOM_SQFT = 50
_MAX_ROOM_SQFT = 400

_SQFT_EXPLICIT_RE = re.compile(
    r"(?<![x×]\s)(\d{1,2}(?:,\d{3})+|\d{2,4})\s*(?:sq\.?\s*ft\.?|sqft|square\s*feet?)",
    re.IGNORECASE,
)

_DIMENSION_SQFT_RE = re.compile(
    r"(\d{1,2})\s*['']?\s*[x×]\s*(\d{1,2})\s*['']?\s*(?:sq\.?\s*ft\.?|sqft|square\s*feet?)",
    re.IGNORECASE,
)

_DIMENSION_RE = re.compile(
    r"(\d{1,2})\s*['']?\s*[x×]\s*(\d{1,2})\s*['']?(?:\s*(?:ft|feet|foot))?(?!\s*(?:sq\.?\s*ft|sqft|square\s*feet))",
    re.IGNORECASE,
)

LARGE_SIZE_SIGNALS = (
    "large room",
    "spacious",
    "big bedroom",
    "master bedroom",
    "huge room",
    "generous",
)

SIZE_TIER_VALUES = ("large", "ok", "small", "unknown")

_MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_MOVE_IN_IMMEDIATE_RE = re.compile(
    r"(?:"
    r"\bavailable\s+now\b"
    r"|\basap\b"
    r"|\bimmediately\b"
    r"|\bimmediate\s+move[- ]?in\b"
    r"|\bmove[- ]?in\s+ready\b"
    r"|\bready\s+now\b"
    r"|\bavailable\s+today\b"
    r"|\bmove\s+in\s+today\b"
    r"|\btoday\b"
    r")",
    re.IGNORECASE,
)

_MOVE_IN_FLEXIBLE_RE = re.compile(
    r"\b(?:flexible|negotiable)\s+(?:move[- ]?in|date|start)\b"
    r"|\bmove[- ]?in\s+(?:flexible|negotiable)\b"
    r"|\bflexible\s+on\s+move[- ]?in\b",
    re.IGNORECASE,
)

_MOVE_IN_MONTH_DAY_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
    re.IGNORECASE,
)

_MOVE_IN_SLASH_DATE_RE = re.compile(
    r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b",
)

_MOVE_IN_AVAILABLE_MONTH_RE = re.compile(
    r"\bavailable\s+(?:on\s+)?"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)

_MOVE_IN_QUALIFIER_RE = re.compile(
    r"\b(early|mid|late)[- ]?"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b",
    re.IGNORECASE,
)

_MOVE_IN_LATE_JULY_RE = re.compile(
    r"(?:"
    r"\blate[- ]?july\b"
    r"|\bend of july\b"
    r"|\bavailable\s+(?:in\s+)?late[- ]?july\b"
    r"|\bmove[- ]?in\s+late[- ]?july\b"
    r")",
    re.IGNORECASE,
)

_MOVE_IN_AUGUST_RE = re.compile(
    r"(?:"
    r"\bavailable\s+(?:in\s+)?aug(?:ust)?\b"
    r"|\bmove[- ]?in\s+(?:in\s+)?aug(?:ust)?\b"
    r"|\baug(?:ust)?\s+(?:move[- ]?in|availability|available)\b"
    r"|\bopening\s+(?:in\s+)?aug(?:ust)?\b"
    r")",
    re.IGNORECASE,
)

_SF_OAKLAND_LOW_PRICE_AREAS = (
    tuple(
        term
        for cfg in LOCATION_PREFERENCES["tiers"].values()
        for term in cfg["terms"]
    )
    + tuple(
        term
        for cfg in LOCATION_PREFERENCES["penalize"].values()
        for term in cfg["terms"]
    )
    + OAKLAND_TERMS
    + (
        "san francisco",
        "sf ",
        " sf",
        "mission",
        "castro",
        "noe",
        "bernal",
        "hayes",
        "soma",
        "inner sunset",
        "outer mission",
        "excelsior",
        "bayview",
        "richmond district",
        "sunset",
    )
)


def _api_key() -> str:
    for key in (GCP_KEY, GENERATIVE_LANGUAGE_API_KEY):
        if key and key.strip():
            return key.strip()
    raise RuntimeError("No API key in .env (GCP_KEY or generative_language_api_key)")


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": (row.get("title") or "")[:120],
        "price": row.get("price"),
        "neighborhood": row.get("neighborhood"),
        "move_in": row.get("move_in_date"),
        "desc": (row.get("description") or "")[:300],
    }


def _prompt(batch: list[dict[str, Any]]) -> str:
    return f"""Score each rental listing against the user criteria. Return ONLY valid JSON.

USER CRITERIA:
{json.dumps(CRITERIA, indent=2)}

LISTINGS:
{json.dumps([_compact(r) for r in batch], indent=2)}

Output schema:
{{
  "results": [
    {{
      "id": "<listing id string>",
      "score": <0-100>,
      "is_private_room": <bool — true if own private bedroom, not shared bedroom>,
      "room_type": "<private_bedroom|shared_house_ok|shared_bedroom_reject|sro_reject>",
      "is_scam_likely": <bool>,
      "move_in_compatible": <bool>,
      "rent_period": "<monthly|weekly|daily|unknown>",
      "short_term_reject": <bool — true if weekly/daily/sublet, not a monthly lease>,
      "sqft": <number or null — parse from "150 sq ft", "10x15", etc.>,
      "size_tier": "<large|ok|small|unknown>",
      "meets_150_sqft": <true|false|null — null if size unknown>,
      "flags": ["short", "tags — include muni_tram_adjacent, caltrain_adjacent, bart_adjacent, muni_bus_only, transit_adjacent, small_household, short_term_reject, meets_150_sqft, small_room_signal, large_room_signal when applicable"],
      "reasoning": "<one line, max 120 chars>"
    }}
  ]
}}

Scoring guidance:
- Reject commercial office/workspace subleases (office sublease, coworking, shared workspace, desk rental). Residential rooms with a home office nook are OK.
- Reject short residential subleases/sublets: single-month sublets, a few weeks, fixed night counts, "flat for the stay", date ranges under ~2 months. Long-term sublets are OK.
- Reject listings advertised primarily in Spanish (habitación, se renta cuarto, etc.) unless the title clearly includes English room-for-rent wording.
- User needs MONTHLY rent only. Detect rent period from title/description/price:
  weekly signals: "per week", "/week", "weekly", "wk", "a week", "$650/week"
  daily/nightly: "per night", "/night", "daily", "nightly", "$49/day", "airbnb"
  monthly signals: "per month", "/month", "monthly", "/mo", "per mo"
  Set short_term_reject=true and cap score at 30 for weekly/daily/sublets.
  If price < $400 in SF/Oakland without explicit monthly, treat as suspicious short-term.
  In reasoning, note effective monthly (~weekly*4.33) when period is weekly/daily.
- Accept private bedroom OR own room in small shared house (~3 people, shared kitchen/bath OK).
- Do NOT penalize shared kitchen/bathroom/house — only reject shared BEDROOM, SRO/hostel, curtain rooms.
- Boost small households: 3br, 2 roommates, 3-person house (add flag small_household).
- Transit bonus ONLY when Muni Metro/tram or Caltrain is within 10 minutes walk (+transit_10min_bonus, +muni_tram_adjacent or +caltrain_adjacent). NOT BART — tag bart_adjacent but no boost. Generic Muni bus (+muni_bus_only) is weaker.
- User is currently in SOMA and prefers SF city center: boost SOMA/South Beach/Mission Bay (+soma_adjacent), Financial District/Embarcadero/Civic Center (+city_center), Hayes Valley/Inner Mission/Potrero (+central_adjacent).
- Homes near Caltrain stations work too: tag +caltrain_adjacent and +caltrain_corridor for 4th & King, Bayshore, Dogpatch, Peninsula stations, or any "near Caltrain" / walk-to-station language. Do NOT apply outer_sf_penalty when Caltrain is mentioned.
- Oakland near BART is acceptable but secondary to central SF.
- Prioritize August move-in (Aug 2–Sep 1 ideal; early August maybe). Deprioritize "available now" and unknown dates.
- Penalize outer SF: Outer Sunset, Parkside, Ingleside, Excelsior, Bayview (+outer_sf_penalty) UNLESS Caltrain-adjacent; $700–800 in Excelsior/Oakland east is normal rent — do not treat as scam.
- Penalize Berkeley and East Bay outside Oakland.
- Penalize Daly City unless clearly BART-adjacent.
- Room size: only penalize explicit sqft under 100. 150+ sq ft is a nice-to-have, not required.
  Parse sqft from title/description: "150 sq ft", "150sqft", "150 square feet", "10x15" (compute 150).
  "Small room", "tiny room", "cozy room" keywords are neutral — do not penalize.
  Large signals (mild boost): "large room", "spacious", "big bedroom", "master bedroom", "huge room", "generous".
  Scoring: explicit sqft >=150 → +5, meets_150_sqft=true; sqft 100–149 → neutral; sqft <100 → cap score at 40;
  large keywords without sqft → +5, size_tier=large. Unknown size → neutral (no penalty).
- 90+ excellent, 70-89 good, 50-69 marginal, <50 poor/scam."""


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _call_gemini(prompt: str) -> dict[str, Any]:
    import google.generativeai as genai

    genai.configure(api_key=_api_key())
    last_err: Exception | None = None

    for model_name in MODEL_FALLBACKS:
        if not model_name:
            continue
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            return _parse_json(response.text)
        except Exception as exc:
            last_err = exc
            continue

    raise RuntimeError(f"All Gemini models failed: {last_err}")


def _mentions_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _mentions_muni_tram(text: str) -> bool:
    if _mentions_any(text, _MUNI_TRAM_CFG["keywords"]):
        return True
    if _mentions_any(text, _MUNI_TRAM_CFG["stations"]):
        return True
    for aliases in _MUNI_TRAM_CFG["lines"].values():
        if _mentions_any(text, aliases):
            return True
    return False


def _detect_muni_line(text: str) -> str | None:
    for line_name, aliases in _MUNI_TRAM_CFG["lines"].items():
        if _mentions_any(text, aliases):
            return line_name
    return None


def _mentions_muni_bus_only(text: str) -> bool:
    if _mentions_muni_tram(text) or _mentions_any(text, _CALTRAIN_TERMS) or _mentions_any(text, _BART_TERMS):
        return False
    if _mentions_any(text, _MUNI_BUS_TERMS):
        return True
    return (
        "muni" in text
        or " bus " in f" {text} "
        or text.startswith("bus ")
        or "bus stop" in text
        or "bus line" in text
    )


_WALK_MINUTES_RE = re.compile(
    r"(?:(?:within|under|less than)\s*)?(\d{1,2})\s*(?:-\s*)?(?:min(?:ute)?s?)"
    r"\s*(?:walk|away|to|from|of)",
    re.IGNORECASE,
)
_CLOSE_WALK_PHRASES = (
    "walk to muni",
    "walk to caltrain",
    "walk to cal train",
    "walking distance to muni",
    "walking distance to caltrain",
    "walking distance to cal train",
    "blocks from muni",
    "blocks from caltrain",
    "blocks from cal train",
    "short walk to muni",
    "short walk to caltrain",
    "short walk to cal train",
    "steps from muni",
    "steps from caltrain",
    "steps from cal train",
    "10 min to muni",
    "10 min to caltrain",
    "10 min to cal train",
    "10-minute walk to muni",
    "10-minute walk to caltrain",
    "5 min walk to muni",
    "5 min walk to caltrain",
    "7 min walk to muni",
    "7 min walk to caltrain",
)
_MUNI_CONTEXT_WORDS = (
    "muni",
    "metro",
    "streetcar",
    "tram",
    "light rail",
    "judah",
    "church line",
    "f-market",
    "e-embarcadero",
    "t-third",
    "k-ingleside",
    "m-ocean",
)
_CALTRAIN_CONTEXT_WORDS = ("caltrain", "cal train", "4th & king", "4th and king", "bayshore")


def _transit_context_is_muni_or_caltrain(window: str) -> bool:
    low = window.lower()
    if _mentions_muni_tram(low) or _mentions_any(low, _CALTRAIN_TERMS):
        return True
    if any(word in low for word in _MUNI_CONTEXT_WORDS + _CALTRAIN_CONTEXT_WORDS):
        return True
    return False


def _muni_caltrain_within_10min(text: str) -> bool:
    """True when listing says Muni Metro/tram or Caltrain is within ~10 min walk."""
    low = text.lower()
    max_minutes = int(TRANSIT_PREFERENCES.get("max_walk_minutes", 10))
    if not (_mentions_muni_tram(low) or _mentions_any(low, _CALTRAIN_TERMS)):
        return False
    for phrase in _CLOSE_WALK_PHRASES:
        if phrase in low:
            return True
    for match in _WALK_MINUTES_RE.finditer(low):
        try:
            minutes = int(match.group(1))
        except ValueError:
            continue
        if minutes > max_minutes:
            continue
        start = max(0, match.start() - 60)
        end = min(len(low), match.end() + 80)
        window = low[start:end]
        if "bart" in window and not _transit_context_is_muni_or_caltrain(window):
            continue
        if _transit_context_is_muni_or_caltrain(window):
            return True
    return False


def _classify_transit_tier(text: str) -> tuple[str, str | None]:
    """Return (tier, optional line name for Muni Metro)."""
    if _mentions_muni_tram(text):
        return "muni_tram", _detect_muni_line(text)
    if _mentions_any(text, _CALTRAIN_TERMS):
        return "caltrain", None
    if _mentions_any(text, _BART_TERMS):
        return "bart", None
    if _mentions_muni_bus_only(text):
        return "muni_bus", None
    return "none", None


def _is_transit_adjacent(text: str) -> bool:
    tier, _ = _classify_transit_tier(text)
    if tier in ("muni_tram", "caltrain"):
        return _muni_caltrain_within_10min(text)
    if tier == "bart":
        return False
    return tier == "muni_bus"


def _transit_tier_boost(tier: str, text: str = "") -> int:
    if tier == "none" or tier == "bart":
        return 0
    if tier in ("muni_tram", "caltrain"):
        if _muni_caltrain_within_10min(text):
            return TRANSIT_PREFERENCES["tiers"][tier]["boost"]
        return 0
    return TRANSIT_PREFERENCES["tiers"][tier]["boost"]


def _transit_tier_flag(tier: str) -> str | None:
    if tier == "none":
        return None
    return TRANSIT_PREFERENCES["tiers"][tier]["flag"]


def _transit_tier_label(tier: str, line: str | None = None) -> str:
    if tier == "none":
        return ""
    label = TRANSIT_PREFERENCES["tiers"][tier]["digest_label"]
    if tier == "muni_tram" and line:
        return f"{label} ({line})"
    return label


def _caltrain_location_context(
    *,
    neighborhood: str = "",
    title: str = "",
    url: str = "",
    full_text: str = "",
) -> dict[str, str]:
    return {
        "neighborhood": neighborhood,
        "title": title,
        "url": url,
        "full_text": full_text,
    }


def _is_caltrain_adjacent(
    text: str,
    *,
    neighborhood: str = "",
    title: str = "",
    url: str = "",
) -> bool:
    loc = _caltrain_location_context(
        neighborhood=neighborhood.lower(),
        title=title.lower(),
        url=url.lower(),
        full_text=text.lower(),
    )
    caltrain_terms = (
        _CALTRAIN_TERMS
        + LOCATION_PREFERENCES["tiers"]["caltrain_corridor"]["terms"]
    )
    return _location_match(caltrain_terms, **loc)


def _is_sf_proper_listing(text: str) -> bool:
    """True when listing is SF-proper, not Oakland/East Bay/Daly City."""
    if _is_daly_city(text, text):
        return False
    if _is_oakland(text):
        return False
    if _is_east_bay_penalty(primary=text, full=text):
        return False
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
    if _WEEKLY_RENT_RE.search(text):
        return "weekly", True
    if _DAILY_RENT_RE.search(text):
        return "daily", True
    if _is_short_sublease(text, title=title):
        return "sublet", True
    if _MONTHLY_RENT_RE.search(text):
        return "monthly", False

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


def _month_token_to_number(token: str) -> int | None:
    return _MONTH_NAMES.get(token.lower().strip())


def _safe_move_in_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _infer_move_in_year(month: int, explicit_year: int | None = None) -> int:
    if explicit_year is not None:
        if explicit_year < 100:
            return 2000 + explicit_year
        return explicit_year
    year = MOVE_IN_REFERENCE_TODAY.year
    if month < MOVE_IN_REFERENCE_TODAY.month - 1:
        year += 1
    return year


def _qualifier_to_day(qualifier: str, *, month: int | None = None) -> int:
    q = qualifier.lower()
    if q == "early":
        return 5
    if q == "mid":
        return 12
    if month == 8:
        return MOVE_IN_TARGET_END.day
    return 25


def _extract_move_in_candidates(
    text: str,
    move_in_date_field: str | None = None,
) -> list[tuple[str, date | None, str]]:
    """Return (signal_text, parsed_date_or_none, signal_kind) candidates."""
    candidates: list[tuple[str, date | None, str]] = []
    combined = text
    if move_in_date_field:
        combined = f"{combined} {str(move_in_date_field).lower()}"

    for match in _MOVE_IN_IMMEDIATE_RE.finditer(combined):
        candidates.append((match.group(0).strip().lower(), None, "immediate"))

    if _MOVE_IN_FLEXIBLE_RE.search(combined):
        candidates.append(("flexible move-in", None, "flexible"))

    for match in _MOVE_IN_AVAILABLE_MONTH_RE.finditer(combined):
        month = _month_token_to_number(match.group(1))
        day = int(match.group(2))
        if month is None:
            continue
        year = _infer_move_in_year(month)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"available {match.group(1)} {day}"
        candidates.append((signal, parsed, "date"))

    for match in _MOVE_IN_MONTH_DAY_RE.finditer(combined):
        month = _month_token_to_number(match.group(1))
        day = int(match.group(2))
        if month is None:
            continue
        explicit_year = int(match.group(3)) if match.group(3) else None
        year = _infer_move_in_year(month, explicit_year)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"{match.group(1)} {day}"
        candidates.append((signal, parsed, "date"))

    for match in _MOVE_IN_SLASH_DATE_RE.finditer(combined):
        month = int(match.group(1))
        day = int(match.group(2))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        explicit_year = int(match.group(3)) if match.group(3) else None
        year = _infer_move_in_year(month, explicit_year)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"{month}/{day}"
        candidates.append((signal, parsed, "date"))

    for match in _MOVE_IN_QUALIFIER_RE.finditer(combined):
        month = _month_token_to_number(match.group(2))
        if month is None:
            continue
        day = _qualifier_to_day(match.group(1), month=month)
        year = _infer_move_in_year(month)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"{match.group(1).lower()}-{match.group(2).lower()}"
        candidates.append((signal, parsed, "qualifier"))

    if _MOVE_IN_LATE_JULY_RE.search(combined):
        year = _infer_move_in_year(7)
        candidates.append(("late july", date(year, 7, 25), "qualifier"))

    if _MOVE_IN_AUGUST_RE.search(combined):
        candidates.append(
            ("available in august", date(_infer_move_in_year(8), 8, 10), "qualifier")
        )

    return candidates


def _classify_move_in_date(
    parsed_date: date | None,
    *,
    signal_kind: str,
    signal_text: str = "",
) -> str:
    """Classify move-in vs hard window late July 20 – Aug 18, 2026."""
    if parsed_date is None:
        if signal_kind == "immediate":
            return "risky"
        if signal_kind == "flexible":
            return "unknown"
        return "unknown"

    if parsed_date > MOVE_IN_WINDOW_END:
        return "too_late"

    if parsed_date < MOVE_IN_WINDOW_START:
        return "too_early"

    if MOVE_IN_WINDOW_START <= parsed_date <= MOVE_IN_WINDOW_END:
        return "ideal"

    return "unknown"


def _landlord_wait_likely(move_in_fit: str, *, has_immediate_signal: bool) -> bool | None:
    if move_in_fit == "ideal":
        return True
    if move_in_fit == "maybe":
        return None
    if move_in_fit == "risky":
        if has_immediate_signal:
            return False
        return False
    if move_in_fit == "too_late":
        return False
    return None


def _analyze_move_in(
    text: str,
    move_in_date_field: str | None = None,
) -> dict[str, Any]:
    """Parse move-in signals from listing text and classify fit vs user window."""
    candidates = _extract_move_in_candidates(text, move_in_date_field)
    has_immediate = any(kind == "immediate" for _, _, kind in candidates)
    has_flexible = any(kind == "flexible" for _, _, kind in candidates)

    move_in_signal: str | None = None
    parsed_date: date | None = None
    move_in_fit = "unknown"

    date_candidates = [(s, d, k) for s, d, k in candidates if k in ("date", "qualifier")]
    immediate_candidates = [(s, d, k) for s, d, k in candidates if k == "immediate"]

    if date_candidates:
        best_signal, best_date, best_kind = date_candidates[0]
        best_fit = _classify_move_in_date(
            best_date, signal_kind=best_kind, signal_text=best_signal
        )
        for signal, parsed, kind in date_candidates[1:]:
            fit = _classify_move_in_date(
                parsed, signal_kind=kind, signal_text=signal
            )
            priority = {
                "ideal": 0,
                "maybe": 1,
                "unknown": 2,
                "risky": 3,
                "too_early": 4,
                "too_late": 5,
            }
            if priority.get(fit, 5) < priority.get(best_fit, 5):
                best_signal, best_date, best_fit = signal, parsed, fit
        move_in_signal = best_signal
        parsed_date = best_date
        move_in_fit = best_fit
        if has_immediate and best_fit in ("ideal", "maybe", "unknown"):
            move_in_fit = "risky"
            move_in_signal = immediate_candidates[0][0] if immediate_candidates else "available now"
    elif immediate_candidates:
        move_in_signal = immediate_candidates[0][0]
        move_in_fit = "risky"
    elif has_flexible:
        move_in_signal = "flexible move-in"
        move_in_fit = "ideal"

    landlord_wait = _landlord_wait_likely(move_in_fit, has_immediate_signal=has_immediate)

    return {
        "move_in_signal": move_in_signal,
        "move_in_fit": move_in_fit,
        "landlord_wait_likely": landlord_wait,
        "parsed_date": parsed_date,
    }


def _move_in_fit_note(move_in_fit: str, move_in_signal: str | None) -> str | None:
    signal = move_in_signal or "unspecified"
    notes = {
        "ideal": f"move-in {signal} — late July–Aug 18 OK",
        "maybe": f"move-in {signal} — outside window",
        "risky": "available now — excluded (need late July–Aug 18)",
        "too_early": f"move-in {signal} — before late July",
        "too_late": f"move-in {signal} — after Aug 18",
        "unknown": "move-in unknown — excluded",
    }
    return notes.get(move_in_fit)


def _apply_move_in_scoring(
    *,
    score: int,
    flags: list[str],
    parts: list[str],
    move_in_info: dict[str, Any],
) -> tuple[int, dict[str, Any], list[str], list[str]]:
    """Adjust score/reasoning for move-in fit."""
    move_in_fit = str(move_in_info.get("move_in_fit") or "unknown")
    move_in_signal = move_in_info.get("move_in_signal")

    adjustments = MOVE_IN_SCORING["adjustments"]
    score += adjustments.get(move_in_fit, 0)

    note = _move_in_fit_note(move_in_fit, move_in_signal)
    if note:
        parts.append(note)
    if move_in_fit != "unknown":
        flags.append(f"move_in_{move_in_fit}")

    return score, move_in_info, flags, parts


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
    if "office space" in tit and not _RESIDENTIAL_ROOM_RE.search(tit):
        return True
    return False


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


def _has_sro_signal(text: str) -> bool:
    if "not sro" in text or "no sro" in text:
        return False
    return _mentions_any(text, SRO_TERMS)


def _has_private_bedroom_signal(text: str) -> bool:
    if _has_shared_bedroom_signal(text):
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

    office_sublease = _is_office_sublease(text, title=loc["title"])
    if office_sublease:
        flags.append("office_sublease_reject")

    language_text = f"{loc['title']} {loc['description']}".strip()
    if _is_spanish_promoted_listing(language_text, title=loc["title"]):
        flags.append("spanish_listing_reject")

    oakland_ok = _is_oakland(primary) or _is_oakland(text)
    if oakland_ok:
        flags.append("oakland_ok")

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
        or "spanish_listing_reject" in flags
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
        if oakland_ok and not far_oakland:
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
    if oakland_ok and not far_oakland:
        parts.append("Oakland OK")
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


def _enrich_size(
    item: dict[str, Any],
    listing_text: str,
) -> None:
    """Apply size detection and scoring to a scored result."""
    size_info = _classify_size(listing_text)

    sqft = item.get("sqft")
    if sqft is not None:
        try:
            size_info["sqft"] = int(sqft)
        except (TypeError, ValueError):
            pass

    size_tier = item.get("size_tier")
    if size_tier in SIZE_TIER_VALUES:
        size_info["size_tier"] = size_tier

    meets = item.get("meets_150_sqft")
    if meets is not None:
        size_info["meets_150_sqft"] = bool(meets)

    flags = item.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]

    score = int(item.get("score", 0))
    reasoning_parts = [str(item.get("reasoning", "")).strip()] if item.get("reasoning") else []
    reasoning_parts = [p for p in reasoning_parts if p]

    score, size_info, flags, reasoning_parts = _apply_size_scoring(
        text=listing_text,
        score=score,
        flags=flags,
        parts=reasoning_parts,
        size_info=size_info,
    )

    item["sqft"] = size_info.get("sqft")
    item["size_tier"] = size_info.get("size_tier", "unknown")
    item["meets_150_sqft"] = size_info.get("meets_150_sqft")
    item["flags"] = flags
    item["score"] = max(0, min(100, score))
    item["reasoning"] = "; ".join(reasoning_parts)[:120]


def _enrich_move_in(
    item: dict[str, Any],
    listing_text: str,
    move_in_date_field: str | None = None,
) -> None:
    """Apply move-in signal parsing and scoring to a scored result."""
    move_in_info = _analyze_move_in(listing_text, move_in_date_field)

    flags = item.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]

    score = int(item.get("score", 0))
    reasoning_parts = [str(item.get("reasoning", "")).strip()] if item.get("reasoning") else []
    reasoning_parts = [p for p in reasoning_parts if p]
    reasoning_parts = [
        p for p in reasoning_parts
        if not any(
            token in p.lower()
            for token in (
                "move-in",
                "move in",
                "aug move-in",
                "landlord may not wait",
                "negotiate hold",
                "confirm with landlord",
            )
        )
    ]

    score, move_in_info, flags, reasoning_parts = _apply_move_in_scoring(
        score=score,
        flags=flags,
        parts=reasoning_parts,
        move_in_info=move_in_info,
    )

    item["move_in_signal"] = move_in_info.get("move_in_signal")
    item["move_in_fit"] = move_in_info.get("move_in_fit", "unknown")
    item["landlord_wait_likely"] = move_in_info.get("landlord_wait_likely")
    item["move_in_compatible"] = move_in_info.get("move_in_fit") in ("ideal", "maybe")
    item["flags"] = flags
    item["score"] = max(0, min(100, score))
    item["reasoning"] = "; ".join(reasoning_parts)[:120]


def _enrich_rent_period(
    item: dict[str, Any],
    listing_text: str,
    price: int | None,
    *,
    title: str = "",
) -> None:
    """Apply rent-period detection and penalties to a scored result."""
    rent_period = item.get("rent_period")
    short_term_reject = bool(item.get("short_term_reject"))

    if rent_period not in RENT_PERIOD_VALUES:
        rent_period, short_term_reject = _detect_rent_period(listing_text, price, title=title)
    elif rent_period in ("weekly", "daily", "sublet"):
        short_term_reject = True
    elif not short_term_reject:
        _, short_term_reject = _detect_rent_period(listing_text, price, title=title)

    flags = item.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]

    score = int(item.get("score", 0))
    reasoning_parts = [str(item.get("reasoning", "")).strip()] if item.get("reasoning") else []
    reasoning_parts = [p for p in reasoning_parts if p]

    score, rent_period, short_term_reject, flags, reasoning_parts = _apply_rent_period_scoring(
        text=listing_text,
        price=price,
        score=score,
        flags=flags,
        parts=reasoning_parts,
        title=title,
        rent_period=str(rent_period) if rent_period in RENT_PERIOD_VALUES else None,
        short_term_reject=short_term_reject,
    )

    item["rent_period"] = rent_period
    item["short_term_reject"] = short_term_reject
    item["flags"] = flags
    item["score"] = score
    item["reasoning"] = "; ".join(reasoning_parts)[:120]


def score_batch(batch: list[dict[str, Any]], use_gemini: bool = True) -> list[dict[str, Any]]:
    if not batch:
        return []
    if use_gemini:
        try:
            data = _call_gemini(_prompt(batch))
            results = data.get("results", [])
            # Ensure transit_adjacent flag is set when Gemini mentions transit in flags/reasoning
            id_to_row = {str(r["id"]): r for r in batch}
            id_to_text = {
                listing_id: " ".join(
                    str(r.get(k, "")) for k in ("title", "description", "neighborhood")
                ).lower()
                for listing_id, r in id_to_row.items()
            }
            for item in results:
                flags = item.get("flags") or []
                if not isinstance(flags, list):
                    flags = [str(flags)]
                listing_text = id_to_text.get(str(item.get("id")), "")
                transit_tier, muni_line = _classify_transit_tier(listing_text)
                tier_flag = _transit_tier_flag(transit_tier)
                if tier_flag and tier_flag not in flags:
                    flags.append(tier_flag)
                reasoning = str(item.get("reasoning", "")).lower()
                combined_text = f"{listing_text} {reasoning}"
                if transit_tier in ("muni_tram", "caltrain") and _muni_caltrain_within_10min(
                    combined_text
                ):
                    if "transit_10min_bonus" not in flags:
                        flags.append("transit_10min_bonus")
                    if "transit_adjacent" not in flags:
                        flags.append("transit_adjacent")
                elif transit_tier == "muni_bus" and "transit_adjacent" not in flags:
                    flags.append("transit_adjacent")
                item["flags"] = flags
                item["transit_tier"] = transit_tier
                item["transit_detail"] = muni_line
                source_row = id_to_row.get(str(item.get("id")), {})
                loc_tier, loc_adj, loc_flag = _classify_location_tier(
                    listing_text,
                    neighborhood=str(source_row.get("neighborhood") or ""),
                    title=str(source_row.get("title") or ""),
                    url=str(source_row.get("url") or ""),
                )
                item["location_tier"] = loc_tier
                if loc_flag and loc_flag not in flags:
                    flags.append(loc_flag)
                    item["flags"] = flags
                if loc_adj and loc_tier in LOCATION_PREFERENCES["tiers"]:
                    item["score"] = max(0, min(100, int(item.get("score", 0)) + loc_adj))
                elif loc_adj and loc_tier in LOCATION_PREFERENCES["penalize"]:
                    item["score"] = max(0, min(100, int(item.get("score", 0)) + loc_adj))
                _ensure_room_type_flags(item, listing_text)
                _enrich_rent_period(
                    item,
                    listing_text,
                    source_row.get("price"),
                    title=str(source_row.get("title") or ""),
                )
                _enrich_size(item, listing_text)
                _enrich_move_in(item, listing_text, source_row.get("move_in_date"))
            return results
        except Exception as exc:
            print(f"  warning: Gemini unavailable ({exc}); using heuristic scorer.", file=sys.stderr)
    return [_heuristic_score(row) for row in batch]


def apply_results(results: list[dict[str, Any]]) -> int:
    saved = 0
    for item in results:
        listing_id = item.get("id")
        if not listing_id:
            continue
        raw_flags = item.get("flags", [])
        if not isinstance(raw_flags, list):
            raw_flags = [str(raw_flags)]
        transit_tier = str(item.get("transit_tier") or "none")
        transit_detail = item.get("transit_detail")
        location_tier = str(item.get("location_tier") or "none")
        rent_period = str(item.get("rent_period") or "unknown")
        short_term_reject = bool(item.get("short_term_reject", False))
        sqft_raw = item.get("sqft")
        sqft = int(sqft_raw) if sqft_raw is not None else None
        size_tier = str(item.get("size_tier") or "unknown")
        meets_raw = item.get("meets_150_sqft")
        meets_150_sqft = bool(meets_raw) if meets_raw is not None else None
        move_in_fit = str(item.get("move_in_fit") or "unknown")
        landlord_raw = item.get("landlord_wait_likely")
        landlord_wait_likely = (
            bool(landlord_raw) if landlord_raw is not None else None
        )
        save_score(
            listing_id=str(listing_id),
            score=int(item.get("score", 0)),
            is_private_room=bool(item.get("is_private_room", False)),
            is_scam_likely=bool(item.get("is_scam_likely", False)),
            move_in_compatible=bool(item.get("move_in_compatible", False)),
            flags=_pack_flags(
                raw_flags,
                transit_tier,
                transit_detail,
                location_tier=location_tier,
                rent_period=rent_period,
                short_term_reject=short_term_reject,
                sqft=sqft,
                size_tier=size_tier,
                meets_150_sqft=meets_150_sqft,
                move_in_signal=item.get("move_in_signal"),
                move_in_fit=move_in_fit,
                landlord_wait_likely=landlord_wait_likely,
            ),
            reasoning=str(item.get("reasoning", "")),
        )
        saved += 1
    return saved


def _score_listings(
    listings: list[dict[str, Any]],
    *,
    use_gemini: bool = True,
    label: str = "listing",
) -> int:
    total = 0
    for offset in range(0, len(listings), BATCH_SIZE):
        batch = listings[offset : offset + BATCH_SIZE]
        print(f"Scoring batch of {len(batch)} {label}(s)…")
        results = score_batch(batch, use_gemini=use_gemini)
        n = apply_results(results)
        total += n
        print(f"  → saved {n} score(s)")
    return total


def run(*, rescore_all: bool = False, use_gemini: bool = True) -> int:
    """Score listings. Returns total scored."""
    init_db()
    if count_listings() == 0:
        print("No listings found — seeding 3 test listings.")
        seed_test_listings()

    if rescore_all:
        listings = get_all_listings()
        if not listings:
            return 0
        print(f"Re-scoring all {len(listings)} listing(s)…")
        return _score_listings(listings, use_gemini=use_gemini, label="listing")

    total = 0
    while True:
        batch = get_unscored_listings(limit=BATCH_SIZE)
        if not batch:
            break
        total += _score_listings(batch, use_gemini=use_gemini, label="unscored listing")
        if len(batch) < BATCH_SIZE:
            break
    return total


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score room listings against user criteria.")
    parser.add_argument(
        "--rescore-all",
        action="store_true",
        help="Re-score every listing in the database (not only unscored).",
    )
    parser.add_argument(
        "--heuristic-only",
        action="store_true",
        help="Skip Gemini API and use local heuristic scorer only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        total = run(rescore_all=args.rescore_all, use_gemini=not args.heuristic_only)
        if total == 0:
            print("No listings to process.")
        else:
            action = "Re-scored" if args.rescore_all else "Scored"
            print(f"Done. {action} {total} listing(s).")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())