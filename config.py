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
    "move_in_start": date(2026, 7, 20),
    "move_in_end": date(2026, 8, 18),
    "move_in_hard_reject_after": date(2026, 8, 19),
    "move_in_flex_weeks": 0,
    "use_filter_not_score": True,
    "move_in_window": {
        "target": "late July – Aug 18, 2026",
        "start": "July 20 (late July)",
        "end": "August 18",
        "accept_examples": [
            "July 20",
            "July 25",
            "late July",
            "August 1",
            "Aug 10",
            "Aug 18",
        ],
        "reject_examples": [
            "September 1",
            "after Aug 18",
            "available after August 19th",
            "before July 20",
            "available now",
            "unknown date",
        ],
        "note": (
            "Hard filter: move-in July 20 – Aug 18. Price up to $1300 OK; $800–$1000 preferred. "
            "'Available after August 19th' and later are hard rejects. "
            "Before late July, 'available now', and unknown dates excluded."
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
        "Emeryville",
        "West Oakland",
        "Downtown Oakland",
        "South San Francisco",
    ],
    "location_note": (
        "Only these areas: all of San Francisco, Emeryville, West Oakland, Downtown "
        "Oakland, South San Francisco. Strongly prefer SF with Muni Metro/tram within "
        "~10 min walk. Reject other East Bay (Berkeley, Temescal, Lake Merritt, "
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
        "Emeryville",
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
CRAIGSLIST_URL = (
    "https://sfbay.craigslist.org/search/sfc/roo"
    "?max_price=1300&private_room=1&availabilityMode=0"
)

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
FACEBOOK_MARKETPLACE_SEARCHES = (
    (
        "SF private room",
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        "?query=private%20room&maxPrice=1300&exact=false",
    ),
    (
        "SF room rent",
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        "?query=room%20for%20rent&maxPrice=1300&exact=false",
    ),
    (
        "SF room available",
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        "?query=room%20available&maxPrice=1300&exact=false",
    ),
    (
        "SF bedroom rent",
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        "?query=bedroom%20for%20rent&maxPrice=1300&exact=false",
    ),
    (
        "SF sublet",
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        "?query=sublet%20room&maxPrice=1300&exact=false",
    ),
    (
        "SF roommate",
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        "?query=roommate%20wanted&maxPrice=1300&exact=false",
    ),
    (
        "West Oakland room",
        "https://www.facebook.com/marketplace/oakland/search/"
        "?query=west%20oakland%20room&maxPrice=1300&exact=false",
    ),
    (
        "Downtown Oakland room",
        "https://www.facebook.com/marketplace/oakland/search/"
        "?query=downtown%20oakland%20room&maxPrice=1300&exact=false",
    ),
    (
        "Emeryville room",
        "https://www.facebook.com/marketplace/oakland/search/"
        "?query=emeryville%20room&maxPrice=1300&exact=false",
    ),
    (
        "South SF room",
        "https://www.facebook.com/marketplace/sanfrancisco/search/"
        "?query=south%20san%20francisco%20room&maxPrice=1300&exact=false",
    ),
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
    "emeryville": {
        "label": "Emeryville",
        "terms": ("emeryville",),
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