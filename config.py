"""Central configuration for the SF room-finding pipeline."""

import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()

# --- Search criteria ---
SEARCH_CRITERIA = {
    "max_rent": 1300,
    "price_focus_min": 800,
    "price_focus_max": 1000,
    "price_match_max": 1300,
    "min_acceptable_sqft": 100,
    "nice_to_have_sqft": 150,
    "size_preference_note": (
        "Only penalize explicit sqft under 100. 150+ sq ft is a nice-to-have boost, "
        "not a requirement. 'Small/tiny/cozy room' keywords are neutral."
    ),
    "move_in_start": date(2026, 8, 1),
    "move_in_end": date(2026, 8, 18),
    "move_in_hard_reject_after": date(2026, 8, 19),
    "move_in_flex_weeks": 0,
    "use_filter_not_score": True,
    "move_in_window": {
        "target": "August 1 – Aug 18, 2026",
        "start": "August 1",
        "end": "August 18",
        "accept_examples": [
            "August 1",
            "Aug 1",
            "Aug 10",
            "Aug 18",
            "available in August",
        ],
        "reject_examples": [
            "July",
            "late July",
            "September 1",
            "after Aug 18",
            "available after August 19th",
            "available now",
            "unknown date",
        ],
        "note": (
            "Hard filter: move-in August 1 – Aug 18. Price up to $1300 OK; $800–$1000 preferred. "
            "'Available after August 19th' and later are hard rejects. "
            "July, 'available now', and unknown dates excluded."
        ),
    },
    "room_type": "private_bedroom_or_small_shared_house",
    "room_type_note": (
        "Private bedroom preferred; also OK as 1 of ~3 in a small shared house "
        "(~2 other roommates). Reject: shared bedroom, SRO/hostel, curtain/partition rooms, "
        "commercial office/workspace subleases, short residential subleases, "
        "Spanish-only listings."
    ),
    "current_location": "SOMA",
    "location": [
        "San Francisco (whole city)",
        "West Oakland",
        "Downtown Oakland",
        "South San Francisco",
    ],
    "location_note": (
        "Only these areas: all of San Francisco, West Oakland, Downtown "
        "Oakland, South San Francisco. Strongly prefer SF with Muni Metro/tram within "
        "~10 min walk. Reject other East Bay (Berkeley, Emeryville, Temescal, Lake Merritt, "
        "Hayward, etc.), Daly City, male-only households, and listings over a week old."
    ),
    "transit_priority": (
        "Bonus only for Muni Metro/tram or Caltrain within ~10 min walk — not BART. "
        "Generic Muni bus is a weaker signal."
    ),
    "neighborhoods_preferred": [
        "SOMA",
        "South Beach",
        "Mission Bay",
        "Financial District",
        "Civic Center",
        "Hayes Valley",
        "Inner Mission",
        "Potrero Hill",
        "Embarcadero",
        "Downtown SF",
        "Castro",
        "West Oakland",
        "Downtown Oakland",
        "South San Francisco",
    ],
    "neighborhoods_penalize": [
        "Outer Sunset",
        "Parkside",
        "Ingleside",
        "Excelsior",
        "Oakland east",
        "East Oakland",
        "San Leandro",
        "Daly City",
    ],
    "penalize": [
        "Berkeley",
        "East Bay outside allowed zones",
        "Oakland (except West Oakland)",
        "Daly City",
        "male-only households",
        "obvious scams",
    ],
}

# --- Data sources ---
_CL_SFC_ROO = (
    "https://sfbay.craigslist.org/search/sfc/roo"
    "?max_price=1300&private_room=1&availabilityMode=0"
)

CRAIGSLIST_URL = _CL_SFC_ROO

SOMA_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=soma+room"
SOUTH_BEACH_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=south+beach+room"
MISSION_BAY_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=mission+bay+room"
DOGPATCH_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=dogpatch+room"
POTRERO_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=potrero+hill+room"
CIVIC_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=civic+center+room"
FINANCIAL_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=financial+district+room"
EMBARCADERO_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=embarcadero+room"
HAYES_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=hayes+valley+room"
INNER_MISSION_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=inner+mission+room"
AUGUST_ROOM_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=august+room+available"

WEST_OAKLAND_CRAIGSLIST_URL = (
    "https://sfbay.craigslist.org/search/eby/roo"
    "?max_price=1300&private_room=1&availabilityMode=0"
    "&query=west+oakland"
)

DOWNTOWN_OAKLAND_CRAIGSLIST_URL = (
    "https://sfbay.craigslist.org/search/eby/roo"
    "?max_price=1300&private_room=1&availabilityMode=0"
    "&query=downtown+oakland"
)

EMERYVILLE_CRAIGSLIST_URL = (
    "https://sfbay.craigslist.org/search/eby/roo"
    "?max_price=1300&private_room=1&availabilityMode=0"
    "&query=emeryville"
)

SOUTH_SF_CRAIGSLIST_URL = (
    "https://sfbay.craigslist.org/search/sfc/roo"
    "?max_price=1300&private_room=1&availabilityMode=0"
    "&query=south+san+francisco"
)

# --- Facebook Marketplace (requires: python scout_facebook.py login) ---
_FB_SF_SEARCH = (
    "https://www.facebook.com/marketplace/sanfrancisco/search/"
    "?maxPrice=1300&exact=false&query="
)
_FB_OAK_SEARCH = (
    "https://www.facebook.com/marketplace/oakland/search/"
    "?maxPrice=1300&exact=false&query="
)


def _fb_sf(query: str) -> str:
    from urllib.parse import quote

    return f"{_FB_SF_SEARCH}{quote(query)}"


def _fb_oak(query: str) -> str:
    from urllib.parse import quote

    return f"{_FB_OAK_SEARCH}{quote(query)}"


FACEBOOK_MARKETPLACE_SEARCHES = (
    ("SF private room", _fb_sf("private room")),
    ("SF room rent", _fb_sf("room for rent")),
    ("SF August room", _fb_sf("august room available")),
    ("SOMA room", _fb_sf("soma room")),
    ("South Beach room", _fb_sf("south beach room")),
    ("Mission Bay room", _fb_sf("mission bay room")),
    ("Potrero room", _fb_sf("potrero hill room")),
    ("Civic Center room", _fb_sf("civic center room")),
    ("Financial District room", _fb_sf("financial district room")),
    ("Hayes Valley room", _fb_sf("hayes valley room")),
    ("Inner Mission room", _fb_sf("inner mission room")),
    ("West Oakland room", _fb_oak("west oakland room")),
    ("Downtown Oakland room", _fb_oak("downtown oakland room")),
    ("South SF room", _fb_sf("south san francisco room")),
)

# --- Polling ---
POLL_INTERVAL_HOURS = 6

# --- Database ---
DB_PATH = os.getenv("DB_PATH", "listings.db")

# --- Allowed location zones (whitelist) ---
LOCATION_ALLOWED = {
    "san_francisco": {
        "label": "San Francisco",
        "terms": (
            "san francisco",
            "city of san francisco",
            "sf ",
            " sf",
            "soma",
            "mission",
            "castro",
            "hayes",
            "potrero",
            "embarcadero",
            "financial district",
            "civic center",
            "south beach",
            "mission bay",
            "dogpatch",
            "noe valley",
            "bernal",
            "inner mission",
            "russian hill",
            "north beach",
            "sunset",
            "richmond district",
            "outer richmond",
            "inner richmond",
            "excelsior",
            "bayview",
            "ingleside",
            "parkside",
            "outer sunset",
            "inner sunset",
            "west portal",
            "forest hill",
            "marina",
            "pacific heights",
            "presidio",
            "treasure island",
        ),
        "url_markers": ("/san-francisco-", "sfc/", "search/sfc", "marketplace/sanfrancisco"),
    },
    "west_oakland": {
        "label": "West Oakland",
        "terms": ("west oakland",),
    },
    "downtown_oakland": {
        "label": "Downtown Oakland",
        "terms": ("downtown oakland", "uptown oakland"),
    },
    "south_san_francisco": {
        "label": "South San Francisco",
        "terms": ("south san francisco", "ssf", "94080", "94083"),
    },
}

# --- Hard location exclusions (supplement whitelist) ---
LOCATION_EXCLUDE = {
    "terms": (
        "emeryville",
        "berkeley",
        "albany",
        "el cerrito",
        "richmond",
        "hayward",
        "fremont",
        "san leandro",
        "davis",
        "davis, ca",
        "alameda",
        "pinole",
        "concord",
        "walnut creek",
        "daly city",
        "colma",
        "pittsburg",
        "pittsburgh",
        "antioch",
        "castro valley",
        "vallejo",
        "benicia",
        "el sobrante",
        "livermore",
        "temescal",
        "rockridge",
        "lake merritt",
        "fruitvale",
        "jack london",
        "adams point",
        "grand lake",
        "oakland east",
        "east oakland",
    ),
    "blob_terms": (
        "near oakland zoo",
        "near san leandro",
    ),
}

# --- Legacy move-in keys (filter tags only; ranking uses match.py) ---
MOVE_IN_SCORING = {
    "adjustments": {
        "ideal": 0,
        "maybe": 0,
        "risky": 0,
        "too_late": 0,
        "too_early": 0,
        "unknown": 0,
    },
    "rank_priority": {
        "ideal": 0,
        "maybe": 1,
        "unknown": 2,
        "risky": 3,
        "too_early": 4,
        "too_late": 5,
    },
}

# --- Budget realism for remaining outer SF (not Excelsior / Oakland east) ---
BUDGET_REALISM = {
    "normal_min": 700,
    "normal_max": 850,
    "penalty_relief": 14,
    "far_oakland_penalty": -25,
    "areas": (
        "visitacion valley",
        "bayview",
        "hunters point",
        "parkside",
        "ingleside",
    ),
}

# --- Location preferences (user currently in SOMA; city center preferred) ---
LOCATION_PREFERENCES = {
    "current_location": "SOMA",
    "tiers": {
        "soma_adjacent": {
            "boost": 28,
            "flag": "soma_adjacent",
            "digest_label": "Near SOMA (current area)",
            "terms": (
                "soma",
                "so ma",
                "south of market",
                "south beach",
                "mission bay",
                "rincon hill",
                "transbay",
                "yerba buena",
                "design district",
                "south beach /",
                "soma /",
            ),
        },
        "city_center": {
            "boost": 22,
            "flag": "city_center",
            "digest_label": "SF city center",
            "terms": (
                "financial district",
                "embarcadero",
                "downtown sf",
                "downtown san francisco",
                "civic center",
                "union square",
                "chinatown",
                "nob hill",
                "russian hill",
                "north beach",
                "telegraph hill",
                "tenderloin",
                "van ness",
            ),
        },
        "central_adjacent": {
            "boost": 12,
            "flag": "central_adjacent",
            "digest_label": "Central SF",
            "terms": (
                "hayes valley",
                "inner mission",
                "mission district",
                "mission /",
                "mission,",
                "lower haight",
                "potrero hill",
                "potrero",
                "castro",
                "noe valley",
                "bernal heights",
                "bernal",
                "japantown",
                "lower pacific heights",
            ),
        },
        "caltrain_corridor": {
            "boost": 18,
            "flag": "caltrain_corridor",
            "digest_label": "Near Caltrain",
            "terms": (
                "near caltrain",
                "close to caltrain",
                "walk to caltrain",
                "walking distance to caltrain",
                "blocks from caltrain",
                "caltrain station",
                "caltrain stop",
                "4th & king",
                "4th and king",
                "4th/king",
                "fourth and king",
                "china basin",
                "dogpatch",
                "bayshore",
                "22nd street",
                "22nd st",
            ),
        },
    },
    "penalize": {
        "south_san_francisco": {
            "penalty": -38,
            "flag": "south_sf_penalty",
            "digest_label": "South SF — ~1hr to Market",
            "terms": ("south san francisco", "ssf", "94080", "94083"),
        },
        "outer_sf": {
            "penalty": -22,
            "flag": "outer_sf_penalty",
            "digest_label": "Outer SF — far from city center",
            "terms": (
                "outer sunset",
                "parkside",
                "ingleside",
                "excelsior",
                "outer mission",
                "bayview",
                "visitacion valley",
                "oceanview",
                "hunters point",
                "inglewood",
                "lakeshore",
                "merced heights",
                "sunnyside",
                "inner sunset",
                "outer richmond",
                "richmond district",
                "sunset / parkside",
                "ingleside /",
            ),
        },
    },
}

# --- Transit preferences (10-min walk bonus for muni_tram + caltrain only; not BART) ---
TRANSIT_PREFERENCES = {
    "max_walk_minutes": 10,
    "priority": ["muni_tram", "caltrain", "muni_bus"],
    "tiers": {
        "muni_tram": {
            "boost": 25,
            "flag": "muni_tram_adjacent",
            "digest_label": "Muni Metro",
            "lines": {
                "N-Judah": ("n-judah", "n judah", "judah line", "judah st"),
                "J-Church": ("j-church", "j church", "church line"),
                "K-Ingleside": ("k-ingleside", "k ingleside", "k line", "k/t/m"),
                "T-Third": ("t-third", "t third", "t line"),
                "M-Ocean View": ("m-ocean view", "m ocean view", "m line"),
                "F-Market": ("f-market", "f market", "f line"),
                "E-Embarcadero": ("e-embarcadero", "e embarcadero", "e line"),
            },
            "keywords": (
                "muni metro",
                "muni rail",
                "streetcar",
                "light rail",
                "tram",
                "metro stop",
                "metro station",
                "rail stop",
            ),
            "stations": (
                "church and market",
                "church st",
                "castro",
                "west portal",
                "embarcadero",
                "van ness",
                "16th st mission",
                "16th street mission",
                "24th st mission",
                "24th street mission",
                "balboa park",
                "sunnydale",
                "forest hill",
                "stonestown",
                "taraval",
                "cole valley",
                "church",
                "montgomery",
                "powell",
                "civic center",
                "sfsu",
                "geneva",
                "ocean view",
                "inglewood",
                "ingleside",
                "third street",
                "market street",
            ),
        },
        "caltrain": {
            "boost": 22,
            "flag": "caltrain_adjacent",
            "digest_label": "Caltrain",
            "terms": (
                "caltrain",
                "cal train",
                "near caltrain",
                "close to caltrain",
                "walk to caltrain",
                "walking distance to caltrain",
                "blocks from caltrain",
                "caltrain station",
                "caltrain stop",
                "4th & king",
                "4th and king",
                "4th/king",
                "fourth and king",
                "china basin",
                "dogpatch",
                "bayshore",
                "22nd street",
                "22nd st",
            ),
        },
        "bart": {
            "boost": 0,
            "flag": "bart_adjacent",
            "digest_label": "BART (no bonus)",
            "terms": (
                "bart",
                "walk to bart",
                "blocks from bart",
                "near bart",
                "bart station",
                "bart-adjacent",
                "rockridge",
                "macarthur",
                "glen park",
                "lake merritt",
                "west oakland",
                "12th st",
                "12th street",
                "19th st",
                "19th street",
                "fruitvale",
                "coliseum",
                "downtown oakland",
                "temescal",
                "jack london",
                "montgomery bart",
                "powell bart",
                "civic center bart",
            ),
        },
        "muni_bus": {
            "boost": 5,
            "flag": "muni_bus_only",
            "digest_label": "Muni bus",
            "terms": (
                "muni bus",
                "muni line",
                "bus stop",
                "bus line",
                "muni route",
            ),
        },
    },
}

# --- API keys (from .env) ---
AI_MODEL = os.getenv("AI_MODEL", "gemini-3.5-flash")
GCP_KEY = os.getenv("GCP_KEY", "")
GENERATIVE_LANGUAGE_API_KEY = os.getenv("generative_language_api_key", "")