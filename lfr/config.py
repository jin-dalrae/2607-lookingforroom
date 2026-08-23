"""Central configuration for the SF room-finding pipeline."""

import os
from datetime import date

from dotenv import load_dotenv

from lfr.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()  # also cwd .env if present

# --- Search criteria (August 2026 original user; live criteria via SEARCH_CRITERIA lazy map) ---
ORIGINAL_SEARCH_CRITERIA = {
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
    "require_move_in_window": True,
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
BERNAL_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=bernal+heights+room"
PANHANDLE_CRAIGSLIST_URL = f"{_CL_SFC_ROO}&query=panhandle+room"

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

ORIGINAL_CRAIGSLIST_SEARCHES = (
    ("San Francisco", CRAIGSLIST_URL),
    ("Dogpatch", DOGPATCH_CRAIGSLIST_URL),
    ("Noe Valley", NOE_VALLEY_CRAIGSLIST_URL),
    ("Mission District", MISSION_CRAIGSLIST_URL),
    ("Inner Mission", INNER_MISSION_CRAIGSLIST_URL),
    ("Hayes Valley", HAYES_CRAIGSLIST_URL),
    ("Castro", CASTRO_CRAIGSLIST_URL),
    ("Bernal Heights", BERNAL_CRAIGSLIST_URL),
    ("Panhandle", PANHANDLE_CRAIGSLIST_URL),
    ("Marina", MARINA_CRAIGSLIST_URL),
    ("Chinatown", CHINATOWN_CRAIGSLIST_URL),
    ("North Beach", NORTH_BEACH_CRAIGSLIST_URL),
    ("Russian Hill", RUSSIAN_HILL_CRAIGSLIST_URL),
    ("Downtown SF", DOWNTOWN_SF_CRAIGSLIST_URL),
    ("SOMA", SOMA_CRAIGSLIST_URL),
    ("South Beach", SOUTH_BEACH_CRAIGSLIST_URL),
    ("Mission Bay", MISSION_BAY_CRAIGSLIST_URL),
    ("Potrero Hill", POTRERO_CRAIGSLIST_URL),
    ("Civic Center", CIVIC_CRAIGSLIST_URL),
    ("Financial District", FINANCIAL_CRAIGSLIST_URL),
    ("Embarcadero", EMBARCADERO_CRAIGSLIST_URL),
    ("Van Ness", VAN_NESS_CRAIGSLIST_URL),
    ("August available", AUGUST_ROOM_CRAIGSLIST_URL),
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


ORIGINAL_FACEBOOK_MARKETPLACE_SEARCHES = (
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
ORIGINAL_ZILLOW_SEARCHES = (
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
            "telegraph hill",
            "nob hill",
            "union square",
            "tenderloin",
            "japantown",
            "alamo square",
            "western addition",
            "fisherman's wharf",
            "duboce",
            "fillmore",
            "yerba buena",
            "rincon hill",
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
        "url_markers": (
            "/san-francisco-",
            "san-francisco-ca",
            "sfc/",
            "search/sfc",
            "marketplace/sanfrancisco",
        ),
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
        "mill valley",
        "sausalito",
        "marin",
        "tiburon",
        "larkspur",
        "pacifica",
        "south san francisco",
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
ORIGINAL_LOCATION_PREFERENCES = {
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
GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY", "").strip()
    or (GCP_KEY or "").strip()
    or (GENERATIVE_LANGUAGE_API_KEY or "").strip()
)
HASDATA_API_KEY = (
    os.getenv("HASDATA_API_KEY", "").strip()
    or os.getenv("ZILLOW_API_KEY", "").strip()
)


class _LazyMapping(dict):
    """Dict-like object that re-reads a loader on every access (active user)."""

    def __init__(self, loader):
        super().__init__()
        self._loader = loader

    def _data(self) -> dict:
        data = self._loader()
        return data if isinstance(data, dict) else {}

    def __getitem__(self, key):
        return self._data()[key]

    def get(self, key, default=None):
        return self._data().get(key, default)

    def __iter__(self):
        return iter(self._data())

    def keys(self):
        return self._data().keys()

    def values(self):
        return self._data().values()

    def items(self):
        return self._data().items()

    def __contains__(self, key):
        return key in self._data()

    def __len__(self):
        return len(self._data())

    def __bool__(self):
        return len(self._data()) > 0

    def __repr__(self) -> str:
        return repr(self._data())


class _LazySeq:
    """Sequence that re-reads a loader on iteration (active user scout URLs)."""

    def __init__(self, loader):
        self._loader = loader

    def _data(self):
        return tuple(self._loader())

    def __iter__(self):
        return iter(self._data())

    def __len__(self):
        return len(self._data())

    def __getitem__(self, idx):
        return self._data()[idx]

    def __bool__(self):
        return len(self) > 0

    def __repr__(self) -> str:
        return repr(self._data())


_HOOD_CL_QUERY = {
    "Chinatown": "chinatown room",
    "North Beach": "north beach room",
    "Hayes Valley": "hayes valley room",
    "Mission": "mission district room",
    "Inner Mission": "inner mission room",
    "SOMA": "soma room",
    "South Beach": "south beach room",
    "Financial District": "financial district room",
    "Nob Hill": "nob hill room",
    "Russian Hill": "russian hill room",
    "Telegraph Hill": "telegraph hill room",
    "Civic Center": "civic center room",
    "Union Square": "union square room",
    "Tenderloin": "tenderloin room",
    "Mission Bay": "mission bay room",
    "Dogpatch": "dogpatch room",
    "Noe Valley": "noe valley room",
    "Castro": "castro room",
    "Marina": "marina room",
    "Bernal Heights": "bernal heights room",
    "Panhandle": "panhandle room",
    "Potrero Hill": "potrero hill room",
    "Embarcadero": "embarcadero room",
    "Van Ness": "van ness room",
    "Downtown SF": "downtown sf room",
    "Japantown": "japantown room",
    "Lower Haight": "lower haight room",
    "Alamo Square": "alamo square room",
    "Western Addition": "western addition room",
    "Fillmore": "fillmore room",
    "Duboce Triangle": "duboce triangle room",
    "Mission Dolores": "dolores park room",
    "Fisherman's Wharf": "fisherman wharf room",
    "Rincon Hill": "rincon hill room",
    "Yerba Buena": "yerba buena room",
    "Jackson Square": "jackson square room",
}

_HOOD_ZILLOW_SLUG = {
    "Chinatown": "chinatown-san-francisco-ca",
    "North Beach": "north-beach-san-francisco-ca",
    "Hayes Valley": "hayes-valley-san-francisco-ca",
    "Mission": "mission-district-san-francisco-ca",
    "Inner Mission": "mission-district-san-francisco-ca",
    "SOMA": "south-of-market-san-francisco-ca",
    "South of Market": "south-of-market-san-francisco-ca",
    "South Beach": "south-beach-san-francisco-ca",
    "Financial District": "financial-district-san-francisco-ca",
    "Nob Hill": "nob-hill-san-francisco-ca",
    "Russian Hill": "russian-hill-san-francisco-ca",
    "Telegraph Hill": "telegraph-hill-san-francisco-ca",
    "Civic Center": "civic-center-san-francisco-ca",
    "Union Square": "downtown-san-francisco-ca",
    "Tenderloin": "tenderloin-san-francisco-ca",
    "Mission Bay": "mission-bay-san-francisco-ca",
    "Dogpatch": "dogpatch-san-francisco-ca",
    "Noe Valley": "noe-valley-san-francisco-ca",
    "Castro": "castro-san-francisco-ca",
    "Marina": "marina-district-san-francisco-ca",
    "Bernal Heights": "bernal-heights-san-francisco-ca",
    "Potrero Hill": "potrero-hill-san-francisco-ca",
    "Japantown": "japantown-san-francisco-ca",
    "Lower Haight": "lower-haight-san-francisco-ca",
    "Alamo Square": "alamo-square-san-francisco-ca",
    "Western Addition": "western-addition-san-francisco-ca",
    "Fisherman's Wharf": "fishermans-wharf-san-francisco-ca",
    "Embarcadero": "embarcadero-san-francisco-ca",
    "Rincon Hill": "rincon-hill-san-francisco-ca",
    "Yerba Buena": "yerba-buena-san-francisco-ca",
}

_HOOD_TERMS = {
    "Chinatown": ("chinatown", "94108"),
    "North Beach": ("north beach", "telegraph hill", "94133"),
    "Hayes Valley": ("hayes valley", "hayes", "94102"),
    "Mission": (
        "inner mission",
        "mission district",
        "the mission",
        "mission /",
        "mission,",
        "94110",
    ),
    "Inner Mission": ("inner mission", "94110"),
    "SOMA": ("soma", "so ma", "south of market", "yerba buena", "design district", "94103", "94105"),
    "South Beach": ("south beach", "rincon hill"),
    "Financial District": ("financial district", "94104", "94111"),
    "Nob Hill": ("nob hill", "94109"),
    "Russian Hill": ("russian hill",),
    "Telegraph Hill": ("telegraph hill",),
    "Civic Center": ("civic center", "van ness"),
    "Union Square": ("union square", "downtown sf", "downtown san francisco"),
    "Tenderloin": ("tenderloin",),
    "Mission Bay": ("mission bay", "china basin"),
    "Dogpatch": ("dogpatch",),
    "Noe Valley": ("noe valley",),
    "Castro": ("castro", "upper market"),
    "Marina": ("marina", "marina district", "cow hollow"),
    "Bernal Heights": ("bernal heights", "bernal"),
    "Panhandle": ("panhandle", "nopa", "lower haight"),
    "Potrero Hill": ("potrero hill", "potrero"),
    "Embarcadero": ("embarcadero",),
    "Van Ness": ("van ness",),
    "Downtown SF": ("downtown sf", "downtown san francisco"),
    "Japantown": ("japantown", "japan town"),
    "Lower Haight": ("lower haight", "haight and fillmore"),
    "Alamo Square": ("alamo square",),
    "Western Addition": ("western addition",),
    "Fillmore": ("fillmore district", "the fillmore"),
    "Duboce Triangle": ("duboce triangle", "duboce"),
    "Mission Dolores": ("mission dolores", "dolores park", "dolores heights"),
    "Valencia Corridor": ("valencia corridor", "valencia street", "on valencia"),
    "Fisherman's Wharf": ("fisherman's wharf", "fishermans wharf", "the wharf", "pier 39"),
    "Wharf": ("fisherman's wharf", "the wharf"),
    "Rincon Hill": ("rincon hill",),
    "Yerba Buena": ("yerba buena",),
    "Transbay": ("transbay", "salesforce transit"),
    "Jackson Square": ("jackson square",),
    "Design District": ("design district",),
}

# One ring of adjacent neighborhoods. Named focus areas automatically
# include these even if the user did not list every surrounding hood.
_HOOD_AROUND = {
    "Chinatown": (
        "Financial District",
        "Nob Hill",
        "Telegraph Hill",
        "Union Square",
        "Embarcadero",
        "Russian Hill",
        "Downtown SF",
        "Jackson Square",
        "Tenderloin",
    ),
    "North Beach": (
        "Telegraph Hill",
        "Russian Hill",
        "Fisherman's Wharf",
        "Embarcadero",
        "Chinatown",
        "Wharf",
    ),
    "Hayes Valley": (
        "Civic Center",
        "Lower Haight",
        "Alamo Square",
        "Western Addition",
        "Japantown",
        "Tenderloin",
        "Van Ness",
        "Duboce Triangle",
        "Fillmore",
        "Castro",
    ),
    "Mission": (
        "Inner Mission",
        "Mission Dolores",
        "Potrero Hill",
        "Bernal Heights",
        "Castro",
        "Mission Bay",
        "Noe Valley",
        "Valencia Corridor",
    ),
    "SOMA": (
        "South Beach",
        "Mission Bay",
        "Rincon Hill",
        "Yerba Buena",
        "Financial District",
        "Civic Center",
        "Potrero Hill",
        "Embarcadero",
        "Transbay",
        "Design District",
        "Tenderloin",
        "Union Square",
    ),
    "Inner Mission": ("Mission", "Potrero Hill", "Bernal Heights", "Castro"),
    "South Beach": ("SOMA", "Mission Bay", "Financial District", "Embarcadero"),
}

_SOMA_NEARBY = frozenset({
    "South Beach",
    "Mission Bay",
    "SOMA",
    "Rincon Hill",
    "Yerba Buena",
    "Transbay",
    "Design District",
    "Potrero Hill",
})


def neighborhoods_around_named(
    preferred: list[str] | None,
    extra_nearby: list[str] | None = None,
) -> list[str]:
    """Surrounding hoods for a focus list — one ring, plus any extras the user named."""
    focus = [str(name).strip() for name in (preferred or []) if str(name).strip()]
    extras = [str(name).strip() for name in (extra_nearby or []) if str(name).strip()]
    seen = set(focus)
    around: list[str] = []
    queues = {hood: list(_HOOD_AROUND.get(hood, ())) for hood in focus}
    while queues:
        progressed = False
        for hood in list(queues):
            neighbors = queues[hood]
            if not neighbors:
                queues.pop(hood, None)
                continue
            neighbor = neighbors.pop(0)
            progressed = True
            if neighbor not in seen:
                seen.add(neighbor)
                around.append(neighbor)
        if not progressed:
            break
    for hood in extras:
        if hood not in seen:
            seen.add(hood)
            around.append(hood)
    return around


def get_search_criteria() -> dict:
    from lfr.users import current_user

    return current_user().search_criteria


def get_location_preferences() -> dict:
    from lfr.users import current_user

    user = current_user()
    if user.search_preset == "original":
        return ORIGINAL_LOCATION_PREFERENCES
    return _location_preferences_from_criteria(user.search_criteria)


def _terms_for_hoods(names: list[str]) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for name in names:
        for term in _HOOD_TERMS.get(name, (name.lower(),)):
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return tuple(terms)


def _location_preferences_from_criteria(criteria: dict) -> dict:
    import copy

    prefs = copy.deepcopy(ORIGINAL_LOCATION_PREFERENCES)
    preferred = list(criteria.get("neighborhoods_preferred") or [])
    nearby = list(criteria.get("neighborhoods_nearby") or [])
    around = list(
        criteria.get("neighborhoods_around")
        or neighborhoods_around_named(preferred, nearby)
    )
    prefs["current_location"] = criteria.get("current_location") or (preferred[0] if preferred else "Chinatown")
    core_terms = _terms_for_hoods(preferred)
    around_soma = [n for n in around if n in _SOMA_NEARBY]
    around_center = [n for n in around if n not in _SOMA_NEARBY]
    if core_terms:
        prefs["tiers"]["focus_core"]["terms"] = core_terms
        prefs["tiers"]["focus_core"]["boost"] = 18
        prefs["tiers"]["focus_core"]["digest_label"] = "Focus: " + " / ".join(preferred)
    soma_terms = _terms_for_hoods(around_soma)
    if soma_terms:
        merged = tuple(dict.fromkeys(soma_terms + prefs["tiers"]["soma_adjacent"]["terms"]))
        prefs["tiers"]["soma_adjacent"]["terms"] = merged
        prefs["tiers"]["soma_adjacent"]["boost"] = 12
        prefs["tiers"]["soma_adjacent"]["digest_label"] = "Around SOMA / Mission Bay"
    center_terms = _terms_for_hoods(around_center)
    if center_terms:
        merged = tuple(dict.fromkeys(center_terms + prefs["tiers"]["city_center"]["terms"]))
        prefs["tiers"]["city_center"]["terms"] = merged
        prefs["tiers"]["city_center"]["boost"] = 10
        prefs["tiers"]["city_center"]["digest_label"] = "Around " + " / ".join(preferred)
        prefs["tiers"]["city_center"]["flag"] = "around_focus"
    # Inner-SF leftovers (Potrero / Japantown / Haight) stay a weaker but included band.
    prefs["tiers"]["central_adjacent"]["boost"] = 6
    prefs["tiers"]["central_adjacent"]["digest_label"] = "Central SF near focus areas"
    return prefs


def _cl_rooms_url(max_price: int) -> str:
    return (
        "https://sfbay.craigslist.org/search/sfc/roo"
        f"?max_price={max_price}&private_room=1&availabilityMode=0"
    )


def _cl_apa_url(max_price: int, *, min_bed: int = 1, max_bed: int = 1) -> str:
    return (
        "https://sfbay.craigslist.org/search/sfc/apa"
        f"?max_price={max_price}&min_bedrooms={min_bed}&max_bedrooms={max_bed}"
        "&availabilityMode=0"
    )


def craigslist_search_urls() -> list[tuple[str, str]]:
    from lfr.users import current_user

    user = current_user()
    if user.search_preset == "original":
        return list(ORIGINAL_CRAIGSLIST_SEARCHES)

    criteria = user.search_criteria
    max_price = int(criteria.get("max_rent") or 1500)
    rooms = _cl_rooms_url(max_price)
    urls: list[tuple[str, str]] = [("San Francisco rooms", rooms)]
    if criteria.get("scout_apartments", True):
        urls.append(("SF 1 bed apartments", _cl_apa_url(max_price, min_bed=1, max_bed=1)))
    seen_queries: set[str] = set()
    preferred = list(criteria.get("neighborhoods_preferred") or [])
    around = list(
        criteria.get("neighborhoods_around")
        or neighborhoods_around_named(preferred, list(criteria.get("neighborhoods_nearby") or []))
    )
    for hood in preferred + around:
        query = _HOOD_CL_QUERY.get(hood) or f"{hood.lower()} room"
        if query in seen_queries:
            continue
        seen_queries.add(query)
        urls.append((hood, f"{rooms}&query={query.replace(' ', '+')}"))
    for label, query in (
        ("1r1b room", "1br 1ba"),
        ("2r2b room", "2br 2ba room"),
        ("3r2b room", "3br 2ba room"),
        ("3r3b room", "3br 3ba room"),
    ):
        urls.append((label, f"{rooms}&query={query.replace(' ', '+')}"))
    return urls


def _facebook_search_url(query: str, *, max_price: int) -> str:
    from urllib.parse import quote

    return (
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        f"?maxPrice={max_price}&exact=false&query={quote(query)}"
    )


def facebook_marketplace_searches() -> list[tuple[str, str]]:
    from lfr.users import current_user

    user = current_user()
    if user.search_preset == "original":
        return list(ORIGINAL_FACEBOOK_MARKETPLACE_SEARCHES)

    criteria = user.search_criteria
    max_price = int(criteria.get("max_rent") or 1500)
    queries: list[tuple[str, str]] = [
        ("SF private room", "private room"),
        ("SF room rent", "room for rent"),
        ("SF 1 bedroom", "1 bedroom"),
        ("SF 1br 1ba", "1br 1ba"),
        ("SF 2br 2ba room", "2br 2ba room"),
        ("SF 3br 2ba room", "3br 2ba room"),
        ("SF 3br 3ba room", "3br 3ba room"),
    ]
    preferred = list(criteria.get("neighborhoods_preferred") or [])
    around = list(
        criteria.get("neighborhoods_around")
        or neighborhoods_around_named(preferred, list(criteria.get("neighborhoods_nearby") or []))
    )
    hood_cap = 15
    for hood in (preferred + around)[:hood_cap]:
        queries.append((f"{hood} room", f"{hood.lower()} room"))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name, query in queries:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((name, _facebook_search_url(query, max_price=max_price)))
    return out


def zillow_api_searches() -> list[tuple[str, dict]]:
    """HasData Zillow Listing API searches for the active user."""
    from lfr.users import current_user

    user = current_user()
    criteria = user.search_criteria
    max_price = int(criteria.get("max_rent") or 1500)
    searches: list[tuple[str, dict]] = [
        (
            f"SF rentals under {max_price}",
            {
                "keyword": "San Francisco, CA",
                "type": "forRent",
                "price[max]": max_price,
            },
        ),
        (
            f"SF 1 bed under {max_price}",
            {
                "keyword": "San Francisco, CA",
                "type": "forRent",
                "price[max]": max_price,
                "beds[min]": 1,
                "beds[max]": 1,
            },
        ),
    ]
    if user.search_preset == "original":
        return searches

    preferred = list(criteria.get("neighborhoods_preferred") or [])
    around = list(
        criteria.get("neighborhoods_around")
        or neighborhoods_around_named(preferred, list(criteria.get("neighborhoods_nearby") or []))
    )
    seen: set[str] = set()
    for hood in preferred + around:
        keyword = _HOOD_ZILLOW_KEYWORD.get(hood) or f"{hood}, San Francisco, CA"
        if keyword in seen:
            continue
        seen.add(keyword)
        searches.append(
            (
                f"{hood} rentals",
                {
                    "keyword": keyword,
                    "type": "forRent",
                    "price[max]": max_price,
                },
            )
        )
        if len(seen) >= 8:
            break
    return searches


_HOOD_ZILLOW_KEYWORD = {
    "Chinatown": "Chinatown, San Francisco, CA",
    "North Beach": "North Beach, San Francisco, CA",
    "Hayes Valley": "Hayes Valley, San Francisco, CA",
    "Mission": "Mission District, San Francisco, CA",
    "Inner Mission": "Inner Mission, San Francisco, CA",
    "SOMA": "South of Market, San Francisco, CA",
    "South Beach": "South Beach, San Francisco, CA",
    "Financial District": "Financial District, San Francisco, CA",
    "Nob Hill": "Nob Hill, San Francisco, CA",
    "Russian Hill": "Russian Hill, San Francisco, CA",
    "Telegraph Hill": "Telegraph Hill, San Francisco, CA",
    "Civic Center": "Civic Center, San Francisco, CA",
    "Lower Haight": "Lower Haight, San Francisco, CA",
    "Potrero Hill": "Potrero Hill, San Francisco, CA",
}


def zillow_searches() -> list[tuple[str, str]]:
    from lfr.users import current_user

    user = current_user()
    if user.search_preset == "original":
        return list(ORIGINAL_ZILLOW_SEARCHES)

    criteria = user.search_criteria
    max_price = int(criteria.get("max_rent") or 1500)
    searches = [
        (f"SF rentals under {max_price}", f"https://www.zillow.com/san-francisco-ca/rentals/0-{max_price}_mp/"),
        (
            f"SF 1 bed under {max_price}",
            f"https://www.zillow.com/san-francisco-ca/rentals/1-1_beds/0-{max_price}_mp/",
        ),
    ]
    seen_slugs: set[str] = set()
    preferred = list(criteria.get("neighborhoods_preferred") or [])
    around = list(
        criteria.get("neighborhoods_around")
        or neighborhoods_around_named(preferred, list(criteria.get("neighborhoods_nearby") or []))
    )
    for hood in preferred + around:
        slug = _HOOD_ZILLOW_SLUG.get(hood)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        searches.append(
            (f"{hood} rentals", f"https://www.zillow.com/{slug}/rentals/0-{max_price}_mp/")
        )
        if len(seen_slugs) >= 12:
            break
    return searches


SEARCH_CRITERIA = _LazyMapping(get_search_criteria)
LOCATION_PREFERENCES = _LazyMapping(get_location_preferences)
FACEBOOK_MARKETPLACE_SEARCHES = _LazySeq(facebook_marketplace_searches)
ZILLOW_SEARCHES = _LazySeq(zillow_searches)
CRAIGSLIST_SEARCHES = _LazySeq(craigslist_search_urls)
