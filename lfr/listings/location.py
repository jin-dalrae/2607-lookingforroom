"""Shared location parsing and matching for listings."""

from __future__ import annotations

import re
from typing import Any

from lfr.config import LOCATION_ALLOWED, LOCATION_EXCLUDE

# Cities too far from SF/Oakland BART corridor — hard reject in matches and pool.
FAR_EAST_BAY_EXCLUDE = (
    "pittsburg",
    "pittsburgh",
    "antioch",
    "castro valley",
    "vallejo",
    "benicia",
    "fairfield",
    "livermore",
    "brentwood",
    "discovery bay",
    "el sobrante",
    "sobrante",
    "hercules",
    "rodeo",
    "oakley",
    "byron",
    "tracy",
    "stockton",
)

FB_JUNK_MARKERS = (
    "today's picks",
    "todays picks",
    "getting around",
    "provided by walk score",
    "nearby transit",
    "nearby schools",
    "provided by greatschools",
    "you are currently offline",
    "number of unread notifications",
    "browse all",
    "marketplace access",
    "create new listing",
    "buy and sell groups",
    "edit marketplace settings",
)

_RENTAL_LOCATION_RE = re.compile(
    r"rental location\s*\n\s*([^\n]+)",
    re.IGNORECASE,
)
_LISTED_ADDRESS_RE = re.compile(
    r"\n([0-9][^\n]{8,80},\s*(?:ca|california)\b[^\n]*)",
    re.IGNORECASE,
)
_FB_RENTALS_LINE_RE = re.compile(
    r"rentals\s*\n\s*([^\n]+)",
    re.IGNORECASE,
)
_CITY_STATE_ZIP_RE = re.compile(
    r"^(.+?),\s*([A-Z]{2})(?:,\s*(\d{5}))?$",
    re.IGNORECASE,
)
_CITY_STATE_LINE_RE = re.compile(
    r"^(.+?,\s*(?:CA|California)(?:,\s*\d{5})?)$",
    re.IGNORECASE,
)

_JUNK_LOCATION_LINES = frozenset({
    "apparel",
    "notifications",
    "notification",
    "marketplace",
    "facebook",
    "unknown",
    "see more",
    "filters",
    "create new listing",
    "your listings",
    "inbox",
    "buying",
    "selling",
})

_SF_PRIMARY_MARKERS = (
    "san francisco",
    "city of san francisco",
    "/san-francisco-",
    "sfc/",
    "search/sfc",
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
    "telegraph hill",
    "nob hill",
    "union square",
    "tenderloin",
    "japantown",
    "lower haight",
    "alamo square",
    "sunset",
    "richmond district",
    "outer richmond",
    "inner richmond",
)


def _compile_place_pattern(term: str) -> re.Pattern[str]:
    cleaned = re.escape(term.strip().lower())
    return re.compile(rf"(?<![a-z0-9]){cleaned}(?![a-z0-9])", re.IGNORECASE)


_PLACE_PATTERNS: dict[str, re.Pattern[str]] = {}


def mention_place(text: str, term: str) -> bool:
    """Word-boundary place match — avoids substring hits inside longer tokens."""
    key = term.strip().lower()
    if not key or not text:
        return False
    pattern = _PLACE_PATTERNS.get(key)
    if pattern is None:
        pattern = _compile_place_pattern(key)
        _PLACE_PATTERNS[key] = pattern
    if not pattern.search(text):
        return False
    if key == "san francisco" and mention_place(text, "south san francisco"):
        return False
    return True


def mentions_any_place(text: str, terms: tuple[str, ...]) -> bool:
    return any(mention_place(text, term) for term in terms)


def strip_facebook_page_junk(text: str) -> str:
    """Drop Marketplace chrome and sidebar listings from scraped page text."""
    if not text:
        return ""
    lowered = text.lower()
    cut_at = len(text)
    for marker in FB_JUNK_MARKERS:
        idx = lowered.find(marker)
        if idx != -1:
            cut_at = min(cut_at, idx)
    trimmed = text[:cut_at].strip()
    return trimmed


_PROSE_LOCATION_MARKERS = (
    "available now",
    "please email",
    "reply with",
    "for rent",
    "includes utilities",
    "contact info",
    "tell us about",
    "serious interest",
    "no pets",
    "not a party",
    "furnished room",
    "private room",
    "shared kitchen",
    "i will confirm",
    "starting when",
    "show contact",
    "hablo español",
)


def is_junk_location_line(text: str) -> bool:
    """True for Marketplace chrome or listing titles mistaken as addresses."""
    raw = (text or "").strip()
    if not raw or len(raw) < 3:
        return True
    low = raw.lower()
    if low in _JUNK_LOCATION_LINES:
        return True
    if low.startswith("facebook") or "marketplace" in low:
        return True
    if len(raw) > 80:
        return True
    words = raw.split()
    if len(words) > 10:
        return True
    if raw.count(".") >= 2 or (re.search(r"[.!?]", raw) and len(words) > 4):
        return True
    if len(raw) > 40 and any(marker in low for marker in _PROSE_LOCATION_MARKERS):
        return True
    if re.search(r"\b\d+\s+(?:bed|beds|habitaci[oó]n|ba[ñn]o|bath|baths)\b", low):
        return True
    if re.search(r"\b(?:house|apartment|departamento|casa|condo|studio)\b", low) and "," not in raw:
        return True
    return False


def parse_location_line(text: str) -> str | None:
    """Return a location string when a line looks like an address or CL hood."""
    raw = (text or "").strip()
    if not raw or is_junk_location_line(raw):
        return None
    if _CITY_STATE_LINE_RE.match(raw):
        return raw
    if _CITY_STATE_ZIP_RE.match(raw):
        return raw
    low = raw.lower()
    if "/" in raw:
        if len(raw) > 60 or re.search(r"[.!?]", raw):
            return None
        parts = [part.strip() for part in raw.split("/")]
        if not parts or any(len(part) > 40 for part in parts):
            return None
        return raw
    if low.startswith("city of "):
        return raw
    if re.match(r"^[A-Za-z .'-]+,\s*(?:CA|California)\s*$", raw, re.IGNORECASE):
        return raw
    return None


def parse_city_state_zip(location: str) -> tuple[str, str, str]:
    """Split 'Castro Valley, CA, 94546' into city/state/zip."""
    raw = (location or "").strip()
    if not raw:
        return "", "", ""
    match = _CITY_STATE_ZIP_RE.match(raw)
    if match:
        return match.group(1).strip(), match.group(2).upper(), (match.group(3) or "").strip()
    if "," in raw:
        city, rest = raw.split(",", 1)
        return city.strip(), rest.strip(), ""
    return raw, "", ""


def extract_rental_location(text: str) -> str:
    """Parse Facebook 'Rental Location' or a street address line when present."""
    if not text:
        return ""
    match = _RENTAL_LOCATION_RE.search(text)
    if match:
        candidate = match.group(1).strip()
        if not is_junk_location_line(candidate):
            return candidate
    addr = _LISTED_ADDRESS_RE.search(text)
    if addr:
        candidate = addr.group(1).strip()
        if not is_junk_location_line(candidate):
            return candidate
    rentals = _FB_RENTALS_LINE_RE.search(text)
    if rentals:
        candidate = rentals.group(1).strip()
        if not is_junk_location_line(candidate):
            return candidate
    return ""


def parse_facebook_listing_fields(text: str) -> dict[str, str]:
    """Extract structured location fields from a Marketplace listing page."""
    raw = text or ""
    cleaned = strip_facebook_page_junk(raw)
    rental_location = extract_rental_location(raw) or extract_rental_location(cleaned)

    street_address = ""
    rentals = _FB_RENTALS_LINE_RE.search(raw) or _FB_RENTALS_LINE_RE.search(cleaned)
    if rentals:
        candidate = rentals.group(1).strip()
        if not is_junk_location_line(candidate):
            street_address = candidate

    city, state, zip_code = parse_city_state_zip(rental_location)
    if not city and street_address:
        city, state, zip_code = parse_city_state_zip(street_address)

    rental_address = rental_location or street_address
    display_place = ""
    if city and state:
        display_place = f"{city}, {state}"
    elif city:
        display_place = city

    return {
        "rental_address": rental_address,
        "street_address": street_address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "display_place": display_place,
    }


def resolve_listing_place(row: dict[str, Any]) -> dict[str, str]:
    """Return stored or parsed location fields for any listing."""
    stored_address = str(row.get("rental_address") or "").strip()
    if stored_address and is_junk_location_line(stored_address):
        stored_address = ""
    raw_description = str(row.get("description") or "")
    parsed = parse_facebook_listing_fields(raw_description)
    if stored_address:
        city, state, zip_code = parse_city_state_zip(stored_address)
        if not city:
            city = parsed.get("city", "")
            state = parsed.get("state", "")
            zip_code = parsed.get("zip", "")
        display_place = f"{city}, {state}" if city and state else (city or stored_address)
        return {
            "rental_address": stored_address,
            "street_address": parsed.get("street_address", ""),
            "city": city,
            "state": state,
            "zip": zip_code,
            "display_place": display_place,
        }
    return parsed


def listing_location_context(row: dict[str, Any]) -> dict[str, str]:
    """Build primary (trusted) and full (fallback) location blobs for a listing."""
    raw_description = str(row.get("description") or "")
    description = strip_facebook_page_junk(raw_description)
    place = resolve_listing_place(row)
    rental_location = place.get("rental_address") or extract_rental_location(raw_description) or extract_rental_location(description)
    neighborhood = str(row.get("neighborhood") or "").strip()
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()

    primary_parts = [p for p in (rental_location, place.get("city"), place.get("display_place"), title) if p]
    primary = " ".join(primary_parts).lower()
    full = " ".join([primary, description, url]).lower()

    return {
        "primary": primary,
        "full": full,
        "rental_location": rental_location,
        "rental_address": rental_location,
        "city": place.get("city", ""),
        "state": place.get("state", ""),
        "zip": place.get("zip", ""),
        "display_place": place.get("display_place", ""),
        "description": description,
        "neighborhood": neighborhood,
        "title": title,
        "url": url,
    }


def has_sf_primary_signal(primary: str) -> bool:
    if not primary:
        return False
    if mentions_any_place(primary, _SF_PRIMARY_MARKERS):
        return True
    if "richmond" in primary and any(
        phrase in primary
        for phrase in ("richmond district", "outer richmond", "inner richmond", "san francisco")
    ):
        return True
    return False


def is_far_east_bay_location(
    *,
    primary: str = "",
    full: str = "",
    rental_location: str = "",
) -> bool:
    """True when the listing's actual location is far East Bay (e.g. Pittsburg)."""
    # Stockton St / similar SF streets must not count as Stockton, CA.
    if has_sf_primary_signal(primary) or has_sf_primary_signal((rental_location or "").lower()):
        return False
    checks = [rental_location, primary]
    for blob in checks:
        if blob and mentions_any_place(blob, FAR_EAST_BAY_EXCLUDE):
            return True
    if full and mentions_any_place(full, FAR_EAST_BAY_EXCLUDE):
        return True
    return False


def is_config_excluded_location(row: dict[str, Any]) -> bool:
    """Hard rejects from config (Excelsior, far Oakland, etc.) using primary location first."""
    ctx = listing_location_context(row)
    hood = ctx["neighborhood"].lower()
    primary = ctx["primary"]
    blob = ctx["full"]

    for term in LOCATION_EXCLUDE["terms"]:
        if mention_place(hood, term) or mention_place(primary, term):
            return True
    for term in LOCATION_EXCLUDE.get("blob_terms", ()):
        if mention_place(primary, term):
            return True
        if not has_sf_primary_signal(primary) and mention_place(blob, term):
            return True
    # FB / thin metadata: hood often only appears in description body
    for term in LOCATION_EXCLUDE.get("full_text_terms", ()):
        if mention_place(blob, term) or mention_place(hood, term) or mention_place(primary, term):
            return True
    # ZIP-based hard excludes (outer SF when neighborhood label is missing)
    zip_code = (ctx.get("zip") or "").strip()
    exclude_zips = LOCATION_EXCLUDE.get("zips") or ()
    if zip_code and zip_code in exclude_zips:
        return True
    for z in exclude_zips:
        if z in primary or z in hood or z in blob:
            # Avoid false hits inside longer numbers
            if re.search(rf"(?<!\d){re.escape(z)}(?!\d)", f"{primary} {hood} {blob}"):
                return True
    return False


NY_CITY_TERMS = (
    "new york",
    "nyc",
    "manhattan",
    "brooklyn",
    "queens",
    "bronx",
    "staten island",
    "harlem",
    "astoria",
    "bushwick",
    "williamsburg",
    "bed-stuy",
    "bedford-stuyvesant",
    "long island city",
    "park slope",
    "greenpoint",
    "jackson heights",
    "sunnyside",
    "flushing",
    "ronkonkoma",
    "hempstead",
    "woodhaven",
    "long island",
    "nassau",
    "suffolk",
    "upper east side",
    "upper west side",
    "east village",
    "west village",
)

_NY_CITY_LABELS = frozenset({
    "new york",
    "nyc",
    "manhattan",
    "brooklyn",
    "queens",
    "bronx",
    "harlem",
    "astoria",
    "bushwick",
    "williamsburg",
    "ronkonkoma",
    "hempstead",
    "woodhaven",
    "long island",
})


def is_new_york_location(
    *,
    primary: str = "",
    rental_location: str = "",
    city: str = "",
    neighborhood: str = "",
    url: str = "",
) -> bool:
    """True when the listing is in New York, not San Francisco."""
    city_low = (city or "").strip().lower()
    hood_low = (neighborhood or "").strip().lower()
    if city_low in _NY_CITY_LABELS or hood_low in _NY_CITY_LABELS:
        return True
    if city_low.endswith(", ny") or hood_low.endswith(", ny"):
        return True
    url_low = (url or "").lower()
    if any(part in url_low for part in ("/ny/", "-ny-", "_ny_", "new-york", "brooklyn", "manhattan")):
        if "san-francisco" not in url_low and "san francisco" not in url_low:
            return True
    blobs = (city_low, hood_low, (rental_location or "").lower(), (primary or "").lower())
    for blob in blobs:
        if blob and mentions_any_place(blob, NY_CITY_TERMS):
            return True
    return False


_OAKLAND_ONLY_TERMS = (
    "oakland",
    "rockridge",
    "macarthur",
    "lake merritt",
    "fruitvale",
    "temescal",
    "jack london",
    "uptown oakland",
    "downtown oakland",
    "adams point",
    "grand lake",
)


def _url_in_allowed_market(url: str, zone_key: str) -> bool:
    cfg = LOCATION_ALLOWED.get(zone_key, {})
    markers = cfg.get("url_markers") or ()
    low = (url or "").lower()
    return any(marker in low for marker in markers)


def is_san_francisco_location(
    *,
    primary: str = "",
    full: str = "",
    rental_location: str = "",
    city: str = "",
    url: str = "",
) -> bool:
    """True when listing is in San Francisco city (whole city OK)."""
    if is_new_york_location(
        primary=primary,
        rental_location=rental_location,
        city=city,
        url=url,
    ):
        return False
    if is_south_san_francisco_city(
        primary=primary,
        rental_location=rental_location,
        city=city,
    ):
        return False
    city_low = (city or "").strip().lower()
    if city_low in ("oakland", "berkeley", "emeryville", "daly city"):
        return False
    if city_low in ("san francisco", "sf"):
        return True
    if has_sf_primary_signal(primary):
        return True
    sf_terms = LOCATION_ALLOWED["san_francisco"]["terms"]
    if rental_location and mentions_any_place(rental_location.lower(), sf_terms):
        return True
    if mentions_any_place(primary, sf_terms):
        return True
    if _url_in_allowed_market(url, "san_francisco"):
        if not mentions_any_place(primary, _OAKLAND_ONLY_TERMS):
            if not mentions_any_place(primary, ("emeryville",)):
                if not is_south_san_francisco_city(primary=primary, city=city):
                    return True
    if full and has_sf_primary_signal(full):
        return True
    return False


def is_emeryville_location(
    *,
    primary: str = "",
    rental_location: str = "",
    city: str = "",
) -> bool:
    terms = ("emeryville",)
    city_low = (city or "").strip().lower()
    if city_low == "emeryville":
        return True
    if rental_location and mentions_any_place(rental_location.lower(), terms):
        return True
    return mentions_any_place(primary, terms)


def is_west_oakland_location(
    *,
    primary: str = "",
    rental_location: str = "",
    city: str = "",
) -> bool:
    """Detect West Oakland (no longer an allowed zone — used for exclusion/flags)."""
    terms = ("west oakland", "oakland west")
    city_low = (city or "").strip().lower()
    if city_low in ("west oakland", "oakland west"):
        return True
    if rental_location and mentions_any_place(rental_location.lower(), terms):
        return True
    return mentions_any_place(primary, terms)


def is_downtown_oakland_location(
    *,
    primary: str = "",
    rental_location: str = "",
    city: str = "",
) -> bool:
    """Detect Downtown Oakland (no longer an allowed zone — used for exclusion/flags)."""
    terms = ("downtown oakland", "uptown oakland", "oakland downtown")
    city_low = (city or "").strip().lower()
    if city_low in ("downtown oakland", "uptown oakland"):
        return True
    if rental_location and mentions_any_place(rental_location.lower(), terms):
        return True
    return mentions_any_place(primary, terms)


def is_south_san_francisco_city(
    *,
    primary: str = "",
    rental_location: str = "",
    city: str = "",
) -> bool:
    """South San Francisco city — not southern SF neighborhoods (hard-excluded)."""
    terms = ("south san francisco", "south san fran", "ssf", "94080", "94083")
    city_low = (city or "").strip().lower()
    if city_low in ("south san francisco", "ssf"):
        return True
    if rental_location and mentions_any_place(rental_location.lower(), terms):
        return True
    if mention_place(primary, "south san francisco"):
        return True
    if mention_place(primary, "ssf") and "san francisco" not in primary:
        return True
    for zip_code in ("94080", "94083"):
        if zip_code in primary or (rental_location and zip_code in rental_location):
            return True
    return False


def allowed_location_zone(row: dict[str, Any]) -> str | None:
    """Return whitelist zone key when listing is in an allowed area."""
    ctx = listing_location_context(row)
    common = {
        "primary": ctx["primary"],
        "rental_location": ctx["rental_location"],
        "city": ctx["city"],
    }
    # SSF / Oakland / Emeryville are hard-excluded — never return as allowed zones
    if is_south_san_francisco_city(**common):
        return None
    if is_san_francisco_location(
        **common,
        full=ctx["full"],
        url=ctx["url"],
    ):
        return "san_francisco"
    return None


def _parsed_location_excluded(row: dict[str, Any]) -> bool:
    """True when listing detail text proves a disallowed city."""
    place = resolve_listing_place(row)
    ctx = listing_location_context(row)
    for blob in (
        (place.get("city") or "").strip().lower(),
        (place.get("rental_address") or "").strip().lower(),
        ctx["primary"],
    ):
        if not blob:
            continue
        for term in LOCATION_EXCLUDE["terms"]:
            if mention_place(blob, term):
                return True
        if mentions_any_place(blob, FAR_EAST_BAY_EXCLUDE):
            return True
    return False


def is_fb_allowed_for_queue(row: dict[str, Any]) -> bool:
    """Facebook card from an allowed search feed — include unless detail proves exclusion."""
    if str(row.get("source") or "") != "facebook":
        return False
    if not zone_from_search_area_label(str(row.get("neighborhood") or "")):
        return False
    if _parsed_location_excluded(row):
        return False
    return True


def is_allowed_location(row: dict[str, Any]) -> bool:
    """Allowed whitelist zones, or Facebook listings from our allowed search feeds."""
    if allowed_location_zone(row) is not None:
        return True
    return is_fb_allowed_for_queue(row)


def is_excluded_location(row: dict[str, Any]) -> bool:
    """Any location that should never appear in the apply queue."""
    ctx = listing_location_context(row)
    if is_new_york_location(
        primary=ctx["primary"],
        rental_location=ctx["rental_location"],
        city=ctx.get("city") or "",
        neighborhood=ctx.get("neighborhood") or str(row.get("neighborhood") or ""),
        url=ctx.get("url") or str(row.get("url") or ""),
    ):
        return True
    if is_config_excluded_location(row):
        return True
    if is_far_east_bay_location(
        primary=ctx["primary"],
        full=ctx["full"],
        rental_location=ctx["rental_location"],
    ):
        return True
    if not is_allowed_location(row):
        return True
    return False


_SEARCH_AREA_LABELS: dict[str, str] = {
    "sf private room": "San Francisco",
    "sf room rent": "San Francisco",
    "sf room available": "San Francisco",
    "sf bedroom rent": "San Francisco",
    "sf 1 bedroom": "San Francisco",
    "sf 1br 1ba": "San Francisco",
    "sf 2br 2ba room": "San Francisco",
    "sf 3br 2ba room": "San Francisco",
    "sf 3br 3ba room": "San Francisco",
    "sf sublet": "San Francisco",
    "sf roommate": "San Francisco",
    "chinatown room": "Chinatown",
    "hayes valley room": "Hayes Valley",
    "mission room": "Mission",
    "soma room": "SOMA",
    "north beach room": "North Beach",
    # Legacy labels (no longer scouted / not allowed zones)
    "south sf room": "South San Francisco",
    "west oakland room": "West Oakland",
    "downtown oakland room": "Downtown Oakland",
    "emeryville room": "Emeryville",
}

_DISPLAY_AREA_TO_ZONE: dict[str, str] = {
    "San Francisco": "san_francisco",
    "Chinatown": "san_francisco",
    "North Beach": "san_francisco",
    "Hayes Valley": "san_francisco",
    "Mission": "san_francisco",
    "Mission District": "san_francisco",
    "Inner Mission": "san_francisco",
    "SOMA": "san_francisco",
    "South of Market": "san_francisco",
    "South Beach": "san_francisco",
    "Financial District": "san_francisco",
    "Nob Hill": "san_francisco",
    "Russian Hill": "san_francisco",
    "Telegraph Hill": "san_francisco",
    "Civic Center": "san_francisco",
    "Union Square": "san_francisco",
    "Tenderloin": "san_francisco",
    "Japantown": "san_francisco",
    "Lower Haight": "san_francisco",
    "Alamo Square": "san_francisco",
    "Western Addition": "san_francisco",
    "Fillmore": "san_francisco",
    "Duboce Triangle": "san_francisco",
    "Mission Dolores": "san_francisco",
    "Potrero Hill": "san_francisco",
    "Bernal Heights": "san_francisco",
    "Castro": "san_francisco",
    "Noe Valley": "san_francisco",
    "Mission Bay": "san_francisco",
    "Embarcadero": "san_francisco",
    "Rincon Hill": "san_francisco",
    "Yerba Buena": "san_francisco",
    "Fisherman's Wharf": "san_francisco",
    "Downtown SF": "san_francisco",
    "Jackson Square": "san_francisco",
    "Van Ness": "san_francisco",
    # South SF / Oakland / Emeryville deliberately omitted — not allowed zones
}


def zone_from_search_area_label(text: str) -> str | None:
    """Map a Facebook search-area label to a whitelist zone key."""
    label = clean_display_area(text)
    return _DISPLAY_AREA_TO_ZONE.get(label)


def clean_display_area(text: str) -> str:
    """Strip Facebook chrome from area labels shown in the UI."""
    if not text:
        return ""
    cleaned = re.sub(r"^facebook\s*·\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^facebook\s+", "", cleaned, flags=re.IGNORECASE).strip()
    low = cleaned.lower()
    if low in ("facebook", "facebook marketplace"):
        return ""
    if low in _SEARCH_AREA_LABELS:
        return _SEARCH_AREA_LABELS[low]
    for suffix in (" private room", " room rent", " sublet", " room"):
        if low.endswith(suffix):
            base = cleaned[: -len(suffix)].strip()
            base_low = base.lower()
            if base_low in _SEARCH_AREA_LABELS:
                return _SEARCH_AREA_LABELS[base_low]
            if base_low == "sf":
                return "San Francisco"
            if base:
                return base
    return cleaned


def is_fb_search_area_label(text: str) -> bool:
    """True when neighborhood is our Marketplace search name, not the rental city."""
    return zone_from_search_area_label(text) is not None


def resolve_display_area(row: dict[str, Any]) -> str:
    """Human area label for tables — never includes Facebook source chrome."""
    place = resolve_listing_place(row)
    for candidate in (
        place.get("display_place"),
        place.get("city"),
    ):
        cleaned = clean_display_area(str(candidate or ""))
        if cleaned and cleaned.lower() not in ("unknown", "facebook marketplace"):
            return cleaned

    inferred = resolve_neighborhood_from_text(
        title=str(row.get("title") or ""),
        description=str(row.get("description") or ""),
        fallback="",
    )
    cleaned = clean_display_area(inferred)
    if cleaned and cleaned.lower() not in ("unknown", "facebook marketplace"):
        return cleaned

    hood = str(row.get("neighborhood") or "")
    if str(row.get("source") or "") == "facebook" and is_fb_search_area_label(hood):
        return "Unknown"
    if hood and not is_junk_location_line(hood):
        cleaned = clean_display_area(hood)
        if cleaned and cleaned.lower() not in ("unknown", "facebook marketplace"):
            return cleaned
    return "Unknown"


def resolve_neighborhood_from_text(
    *,
    title: str = "",
    description: str = "",
    fallback: str = "",
) -> str:
    """Infer display place from Facebook rental address when available."""
    fields = parse_facebook_listing_fields(description)
    if fields.get("display_place"):
        return fields["display_place"]
    if fields.get("rental_address"):
        city, _, _ = parse_city_state_zip(fields["rental_address"])
        if city:
            return city
    cleaned = strip_facebook_page_junk(description)
    blob = f"{title} {cleaned}".lower()
    for label in (
        "South San Francisco",
        "West Oakland",
        "Downtown Oakland",
        "Emeryville",
        "San Francisco",
        "SOMA",
        "Mission",
    ):
        if mention_place(blob, label.lower()):
            return label
    return fallback


def clean_listing_description(description: str | None) -> str | None:
    if not description:
        return None
    cleaned = strip_facebook_page_junk(description)
    return cleaned or None


def _hood_from_title(title: str) -> str:
    """Pull a short place name from Craigslist-style room titles."""
    raw = (title or "").strip()
    if not raw or len(raw) > 60:
        return ""
    if len(raw.split()) > 12 or re.search(r"[.!?]", raw):
        return ""
    for pattern in (
        r"\broom\s+(?:in|at|near|-)\s+(.+)$",
        r"(?:furnished|private|cozy|spacious|clean|beautiful|new)\s+room\s+(.+)$",
    ):
        match = re.search(pattern, raw, re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip(" -–—")
        if candidate and len(candidate) <= 40 and not is_junk_location_line(candidate):
            return candidate
    return ""


def _extract_street_from_description(description: str) -> str:
    if not description:
        return ""
    match = _LISTED_ADDRESS_RE.search(description)
    if match:
        candidate = match.group(1).strip()
        if not is_junk_location_line(candidate):
            return candidate
    for line in description.splitlines():
        line = line.strip()
        if not line or len(line) > 80:
            continue
        if re.match(r"^\d{1,5}\s+\S", line) and "," in line:
            if not is_junk_location_line(line):
                return line
    return ""


def extract_post_display_address(row: dict[str, Any]) -> str:
    """Address or area as written in the listing post (re-parsed from title + body)."""
    title = str(row.get("title") or "").strip()
    description = str(row.get("description") or "").strip()
    source = str(row.get("source") or "")

    if source == "facebook":
        place = resolve_listing_place(row)
        stored = (place.get("rental_address") or "").strip()
        if stored and not is_junk_location_line(stored):
            return stored

    if source == "craigslist":
        hood = str(row.get("neighborhood") or "").strip()
        if hood and not is_junk_location_line(hood):
            return hood
        street = _extract_street_from_description(description)
        if street:
            return street
        title_hood = _hood_from_title(title)
        if title_hood:
            return title_hood
        inferred = resolve_neighborhood_from_text(
            title=title,
            description=description,
            fallback="",
        )
        if inferred and not is_junk_location_line(inferred):
            return inferred
        loc = parse_location_line(title)
        return loc or ""

    for blob in (description, strip_facebook_page_junk(description)):
        if not blob:
            continue
        rental = extract_rental_location(blob)
        if rental:
            return rental
        fields = parse_facebook_listing_fields(blob)
        rental = (fields.get("rental_address") or "").strip()
        if rental and not is_junk_location_line(rental):
            return rental

    loc = parse_location_line(title)
    if loc:
        return loc

    if description:
        for line in description.splitlines():
            line = line.strip()
            if not line or len(line) > 80:
                continue
            loc = parse_location_line(line)
            if loc:
                return loc

    return ""