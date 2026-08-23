"""Shared scoring constants, regexes, and term tuples."""

from __future__ import annotations

import re
from datetime import date, timedelta

from lfr.config import (
    AI_MODEL,
    LOCATION_PREFERENCES,
    SEARCH_CRITERIA,
    TRANSIT_PREFERENCES,
)

# --- User criteria (hardcoded config) ---
MIN_ACCEPTABLE_SQFT = SEARCH_CRITERIA.get("min_acceptable_sqft") or 100
NICE_TO_HAVE_SQFT = SEARCH_CRITERIA.get("nice_to_have_sqft") or 150
MOVE_IN_FLEX_WEEKS: int = int(SEARCH_CRITERIA.get("move_in_flex_weeks") or 0)
MOVE_IN_TARGET_START: date = SEARCH_CRITERIA.get("move_in_start") or date.today()
MOVE_IN_TARGET_END: date = SEARCH_CRITERIA.get("move_in_end") or date.today()
MOVE_IN_WINDOW_START = MOVE_IN_TARGET_START - timedelta(weeks=MOVE_IN_FLEX_WEEKS)
MOVE_IN_WINDOW_END = MOVE_IN_TARGET_END + timedelta(weeks=MOVE_IN_FLEX_WEEKS)
MOVE_IN_REFERENCE_TODAY = date(2026, 7, 2)
MOVE_IN_FIT_VALUES = ("ideal", "maybe", "risky", "too_early", "too_late", "unknown")

class _Criteria(dict):
    """Scoring criteria with live max_rent from the active user."""

    def __getitem__(self, key):
        if key == "max_rent":
            return SEARCH_CRITERIA.get("max_rent", super().__getitem__(key))
        if key == "current_location":
            return SEARCH_CRITERIA.get("current_location", super().get(key, "SOMA"))
        if key == "wants" and SEARCH_CRITERIA.get("wants"):
            return SEARCH_CRITERIA["wants"]
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


CRITERIA = _Criteria({
    "max_rent": 1300,
    "min_acceptable_sqft": MIN_ACCEPTABLE_SQFT,
    "nice_to_have_sqft": NICE_TO_HAVE_SQFT,
    "move_in_target": "2026-08-01 to 2026-08-18 (August window)",
    "price_focus": "$800–$1000/month",
    "move_in_flex_weeks": 0,
    "wants": (
        "private bedroom in SF or Oakland; also OK as 1 of ~3 people in a small "
        "shared house (~2 other roommates). Prefer private bedroom in a 3-person "
        "household but not required."
    ),
    "location": (
        "Only: whole San Francisco, Emeryville, West Oakland, Downtown Oakland, "
        "South San Francisco (last resort — ~1hr to Market). "
        "Strongly prefer SF with Muni Metro/tram within ~10 min walk (currently in SOMA). "
        "Reject other East Bay, Daly City, and male-only households."
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
        "Berkeley and East Bay outside allowed zones",
        "Oakland except West Oakland",
        "Daly City",
        "male-only / men-only households",
    ],
    "room_type_flags": [
        "private_bedroom",
        "shared_house_ok",
        "shared_bedroom_reject",
        "sro_reject",
    ],
})

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

DALY_CITY_TERMS = ("daly city", "daly-city", "colma")

MALE_HOUSEHOLD_REJECT = (
    "male household",
    "male only",
    "men only",
    "guys only",
    "all male",
    "all-male",
    "naturist male",
    "male roommates only",
    "male roommate only",
    "looking for a male",
    "looking for male",
    "male tenant only",
    "male housemate",
    "for men only",
    "no women",
    "no females",
    "male living",
    "men's house",
    "mens house",
    "male house",
)

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
    "professional office",
    "private office",
    "office space for rent",
    "office for rent",
    "office for lease",
    "for lease: office",
    "not a living space",
    "creative studio for rent",
    "coworking",
    "co-working",
    "co working space",
    "shared workspace",
    "shared office space",
    "workspace sublease",
    "workspace sublet",
    "desk rental",
    "desk space for rent",
    "storage space",
    "storage unit",
    "parking space",
    "parking spot",
    "garage space",
    "garage for rent",
    "car parking",
    "rv space",
    "trailer space",
    "rv lot",
    "boat slip",
    "moorage",
    "booth rental",
    "salon chair",
    "booth rent",
    "salon booth",
    "treatment room",
    "massage room",
)

FURNITURE_GOODS_TERMS = (
    "living room set",
    "dining room set",
    "dining set",
    "bedroom set",
    "solid oak",
    "sectional sofa",
    "for sale",
    "selling ",
    "sell ",
    "dresser",
    "bookcase",
    "bookshelf",
    "coffee table",
    "dining table",
    "area rug",
    "mattress only",
    "mission style desk",
    "office desk",
)

_OFFICE_SUBLEASE_TITLE_RE = re.compile(
    r"(?:office\s+(?:sublease|sublet|space|for\s+rent|for\s+lease)|professional\s+office|private\s+office)",
    re.IGNORECASE,
)

_OFFICE_CONTEXT_RE = re.compile(
    r"\b(?:private\s+office|professional\s+office|office\s+space|creative\s+studio|"
    r"not\s+a\s+living\s+space|coworking|co-working)\b",
    re.IGNORECASE,
)

_ROOM_FOR_RENT_RE = re.compile(
    r"\b(?:room|bedroom)\s+for\s+rent\b",
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
    r"|(?:rent|price|\$\d+)[^\n]{0,40}per\s+week\b"
    r"|per\s+week\b[^\n]{0,40}(?:rent|room)"
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
    r"(?:\b(?:6|9|12)\s*[- ]?month\s+minimum\b|\bone\s+year\b|\b1[- ]?year\b|\b9[- ]?month\b|\b12[- ]?month\b)",
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
    re.compile(r"vacation\s+(?:sub(?:let|lease)|rental)", re.IGNORECASE),
    re.compile(
        r"\b(?:summer|summertime)\s+(?:sub(?:let|lease)|rental|only|stay|housing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:sub(?:let|lease)|rental)\s+(?:for\s+)?(?:the\s+)?summer\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bfor\s+(?:the\s+)?summer\b", re.IGNORECASE),
    re.compile(r"\bonly\s+(?:for\s+)?(?:the\s+)?summer\b", re.IGNORECASE),
    re.compile(r"\bthis\s+summer\s+only\b", re.IGNORECASE),
    re.compile(r"\bduring\s+(?:the\s+)?summer\b", re.IGNORECASE),
    re.compile(r"\bsummer\s+only\b", re.IGNORECASE),
    re.compile(
        r"\b(?:may|june|july)\s*(?:through|thru|to|until|-|–|—)\s*"
        r"(?:july|august|september|sep(?:t)?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:jun|jul)\s*(?:through|thru|to|until|-|–|—)\s*(?:aug|sep(?:t)?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:1|2|3|one|two|three)\s*[- ]?months?\s+"
        r"(?:sub(?:let|lease)|lease|rental|only|stay)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:sub(?:let|lease)|lease|rental)\s+(?:for\s+)?"
        r"(?:1|2|3|one|two|three)\s+months?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\ba\s+few\s+months\b", re.IGNORECASE),
    re.compile(r"\bcouple\s+(?:of\s+)?months\b", re.IGNORECASE),
    re.compile(
        r"\btemporary\s+(?:sub(?:let|lease)|rental|stay|housing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\buntil\s+(?:the\s+end\s+of\s+)?(?:june|july|august)\b",
        re.IGNORECASE,
    ),
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

