"""Central configuration for the SF room-finding pipeline."""

import os
from datetime import date

from dotenv import load_dotenv

from lfr.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()  # also cwd .env if present

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
        "San Francisco — central focus (see preferred list)",
    ],
    "location_note": (
        "Focus SF: Dogpatch, Noe Valley, Mission, Hayes Valley, Castro, Bernal Heights, "
        "near Panhandle, Marina, Chinatown, North Beach, Russian Hill, and nearby downtown "
        "(SOMA, South Beach, Mission Bay, Civic Center, Financial District, Embarcadero, "
        "Potrero Hill). "
        "Hard-reject Richmond, Sunset/Parkside, Ingleside, Excelsior, all of Oakland, "
        "Emeryville, and South San Francisco. "
        "Reject other East Bay, Daly City, male-only households, listings over a week old. "
        "Prefer Muni Metro/tram or Caltrain within ~10 min walk."
    ),
    "transit_priority": (
        "Bonus only for Muni Metro/tram or Caltrain within ~10 min walk — not BART. "
        "Generic Muni bus is a weaker signal."
    ),
    "neighborhoods_preferred": [
        "Dogpatch",
        "Noe Valley",
        "Inner Mission",
        "Mission District",
        "Hayes Valley",
        "Castro",
        "Bernal Heights",
        "Panhandle",
        "Near Panhandle",
        "Lower Haight",
        "NOPA",
        "Marina",
        "Chinatown",
        "North Beach",
        "Russian Hill",
        "SOMA",
        "South Beach",
        "Mission Bay",
        "Potrero Hill",
        "Financial District",
        "Civic Center",
        "Embarcadero",
        "Downtown SF",
    ],
    "neighborhoods_penalize": [
        "Richmond",
        "Outer Richmond",
        "Inner Richmond",
        "Sunset",
        "Outer Sunset",
        "Inner Sunset",
        "Parkside",
        "Ingleside",
        "Excelsior",
        "Oakland",
        "West Oakland",
        "Downtown Oakland",
        "Emeryville",
        "South San Francisco",
        "Oakland east",
        "East Oakland",
        "San Leandro",
        "Daly City",
    ],
    "penalize": [
        "Richmond (SF)",
        "Sunset / Parkside",
        "Ingleside",
        "Excelsior",
        "Oakland (all)",
        "Emeryville",
        "South San Francisco",
        "Berkeley",
        "East Bay",
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
MISSION_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=mission+district+room"
NOE_VALLEY_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=noe+valley+room"
DOWNTOWN_SF_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=downtown+sf+room"
CASTRO_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=castro+room"
MARINA_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=marina+room"
CHINATOWN_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=chinatown+room"
NORTH_BEACH_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=north+beach+room"
RUSSIAN_HILL_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=russian+hill+room"
AUGUST_ROOM_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=august+room+available"
VAN_NESS_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=van+ness+room"

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
    ("Dogpatch room", _fb_sf("dogpatch room")),
    ("Noe Valley room", _fb_sf("noe valley room")),
    ("Mission room", _fb_sf("mission district room")),
    ("Hayes Valley room", _fb_sf("hayes valley room")),
    ("Castro room", _fb_sf("castro room")),
    ("Bernal Heights room", _fb_sf("bernal heights room")),
    ("Panhandle room", _fb_sf("panhandle room")),
    ("Marina room", _fb_sf("marina room")),
    ("Chinatown room", _fb_sf("chinatown room")),
    ("North Beach room", _fb_sf("north beach room")),
    ("Russian Hill room", _fb_sf("russian hill room")),
    ("Downtown SF room", _fb_sf("downtown sf room")),
    ("SOMA room", _fb_sf("soma room")),
    ("South Beach room", _fb_sf("south beach room")),
    ("Mission Bay room", _fb_sf("mission bay room")),
    ("Potrero room", _fb_sf("potrero hill room")),
    ("Civic Center room", _fb_sf("civic center room")),
    ("Financial District room", _fb_sf("financial district room")),
    ("Inner Mission room", _fb_sf("inner mission room")),
)

# --- Zillow (requires Playwright) ---
ZILLOW_SEARCHES = (
    ("SF Rentals under 1300", "https://www.zillow.com/san-francisco-ca/rentals/0-1300_mp/"),
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
            "bernal heights",
            "inner mission",
            "castro",
            "panhandle",
            "lower haight",
            "nopa",
            "north of the panhandle",
            "russian hill",
            "north beach",
            "chinatown",
            "bayview",
            "marina",
            "marina district",
            "cow hollow",
            "pacific heights",
            "presidio",
            "treasure island",
            # Richmond / Sunset / Ingleside / Excelsior hard-excluded via LOCATION_EXCLUDE
            # Oakland / Emeryville hard-excluded — not in whitelist
        ),
        "url_markers": ("/san-francisco-", "sfc/", "search/sfc", "marketplace/sanfrancisco"),
    },
    # South San Francisco hard-excluded — terms kept only for detection helpers below
}

# --- Hard location exclusions (supplement whitelist) ---
LOCATION_EXCLUDE = {
    "terms": (
        # Outer SF — do not surface (user focus: Dogpatch / Noe / Mission / Hayes / downtown)
        "richmond",
        "richmond district",
        "outer richmond",
        "inner richmond",
        "richmond / seacliff",
        "seacliff",
        "sunset",
        "outer sunset",
        "inner sunset",
        "sunset / parkside",
        "sunset district",
        "parkside",
        "ingleside",
        "ingleside / sfsu / ccsf",
        "excelsior",
        "excelsior / outer mission",
        "outer mission",
        # South San Francisco (separate city — not SF)
        "south san francisco",
        "south san fran",
        "ssf",
        # East Bay — all Oakland + Emeryville + far markets (no longer allowed)
        "oakland",
        "west oakland",
        "downtown oakland",
        "uptown oakland",
        "oakland west",
        "oakland east",
        "oakland downtown",
        "oakland north",
        "oakland hills",
        "east oakland",
        "emeryville",
        "berkeley",
        "albany",
        "el cerrito",
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
    ),
    "blob_terms": (
        "near oakland zoo",
        "near san leandro",
        "near sfsu",
        "near sf state",
        "ocean avenue",
        "west portal",
        "forest hill",
    ),
    # Match these in full listing text (FB often puts hood only in body, not neighborhood field)
    "full_text_terms": (
        "richmond district",
        "outer richmond",
        "inner richmond",
        "richmond / seacliff",
        "outer sunset",
        "inner sunset",
        "sunset / parkside",
        "sunset district",
        "in the sunset",
        "in the richmond",
        "ingleside",
        "excelsior",
        "outer mission",
        "parkside",
        "oakland",
        "emeryville",
        "west oakland",
        "downtown oakland",
        "south san francisco",
        "ssf",
    ),
    # ZIP hard-excludes (when hood label is missing / only city+zip)
    "zips": (
        "94112",  # Excelsior / Outer Mission / Ingleside terr.
        "94116",  # Outer Sunset / Parkside
        "94122",  # Inner/Outer Sunset
        "94121",  # Outer Richmond
        "94118",  # Inner Richmond
        "94127",  # West Portal / St. Francis Wood / near Ingleside
        "94132",  # Lakeshore / SFSU / Ingleside
        "94080",  # South San Francisco
        "94083",  # South San Francisco
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

# --- Location preferences (focus: Dogpatch / Noe / Mission / Hayes / downtown) ---
LOCATION_PREFERENCES = {
    "current_location": "SOMA",
    "tiers": {
        "focus_core": {
            "boost": 32,
            "flag": "focus_core",
            "digest_label": "Focus area (central SF + Marina / Chinatown / North Beach / Russian Hill)",
            "terms": (
                "dogpatch",
                "noe valley",
                "hayes valley",
                "inner mission",
                "mission district",
                "mission /",
                "mission,",
                "the mission",
                "castro",
                "castro /",
                "upper market",
                "bernal heights",
                "bernal",
                "panhandle",
                "near the panhandle",
                "near panhandle",
                "north of the panhandle",
                "nopa",
                "lower haight",
                "marina",
                "marina district",
                "marina /",
                "cow hollow",
                "chinatown",
                "north beach",
                "russian hill",
                "telegraph hill",
            ),
        },
        "soma_adjacent": {
            "boost": 28,
            "flag": "soma_adjacent",
            "digest_label": "Near SOMA / downtown",
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
                "nob hill",
                "tenderloin",
                "van ness",
            ),
        },
        "central_adjacent": {
            "boost": 14,
            "flag": "central_adjacent",
            "digest_label": "Central SF",
            "terms": (
                "potrero hill",
                "potrero",
                "japantown",
                "lower pacific heights",
                "haight",
                "cole valley",
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
            "penalty": -40,
            "flag": "outer_sf_penalty",
            "digest_label": "Outer SF — far from focus areas",
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
                "inner richmond",
                "richmond district",
                "richmond / seacliff",
                "sunset / parkside",
                "sunset",
                "ingleside /",
                "west portal",
                "forest hill",
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