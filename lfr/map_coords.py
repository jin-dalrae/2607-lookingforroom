"""Resolve rough map coordinates for listings."""

from __future__ import annotations

import math
import re
from typing import Any

# Neighborhood / area centroids for SF + East Bay room search.
AREA_COORDS: dict[str, tuple[float, float]] = {
    "san francisco": (37.7749, -122.4194),
    "city of san francisco": (37.7749, -122.4194),
    "sf": (37.7749, -122.4194),
    "soma": (37.7786, -122.4056),
    "so ma": (37.7786, -122.4056),
    "south of market": (37.7786, -122.4056),
    "soma / south beach": (37.7786, -122.4056),
    "south beach": (37.7790, -122.3910),
    "mission": (37.7599, -122.4148),
    "the mission": (37.7599, -122.4148),
    "mission district": (37.7599, -122.4148),
    "inner mission": (37.7580, -122.4180),
    "mission dolores": (37.7600, -122.4260),
    "dolores park": (37.7596, -122.4269),
    "dolores heights": (37.7570, -122.4250),
    "valencia corridor": (37.7590, -122.4210),
    "castro": (37.7609, -122.4350),
    "the castro": (37.7609, -122.4350),
    "castro / upper market": (37.7609, -122.4350),
    "eureka valley": (37.7609, -122.4350),
    "upper market": (37.7640, -122.4340),
    "nob hill": (37.7930, -122.4161),
    "lower nob hill": (37.7907, -122.4150),
    "north beach": (37.8061, -122.4103),
    "north beach / telegraph hill": (37.8061, -122.4103),
    "telegraph hill": (37.8015, -122.4058),
    "chinatown": (37.7941, -122.4078),
    "hayes valley": (37.7767, -122.4244),
    "hayes": (37.7767, -122.4244),
    "marina": (37.8030, -122.4365),
    "marina district": (37.8030, -122.4365),
    "cow hollow": (37.7980, -122.4350),
    "pacific heights": (37.7925, -122.4380),
    "lower pacific heights": (37.7860, -122.4360),
    "russian hill": (37.8014, -122.4198),
    "financial district": (37.7946, -122.3999),
    "fidi": (37.7946, -122.3999),
    "embarcadero": (37.7955, -122.3937),
    "civic center": (37.7799, -122.4148),
    "van ness": (37.7840, -122.4194),
    "downtown": (37.7879, -122.4075),
    "downtown sf": (37.7879, -122.4075),
    "union square": (37.7879, -122.4075),
    "tenderloin": (37.7840, -122.4140),
    "mid-market": (37.7800, -122.4140),
    "mid market": (37.7800, -122.4140),
    "japantown": (37.7854, -122.4294),
    "western addition": (37.7820, -122.4310),
    "fillmore": (37.7840, -122.4330),
    "the fillmore": (37.7840, -122.4330),
    "alamo square": (37.7764, -122.4347),
    "nopa": (37.7820, -122.4410),
    "north of panhandle": (37.7820, -122.4410),
    "panhandle": (37.7725, -122.4450),
    "near panhandle": (37.7725, -122.4450),
    "lower haight": (37.7719, -122.4310),
    "haight": (37.7692, -122.4480),
    "haight-ashbury": (37.7692, -122.4480),
    "haight ashbury": (37.7692, -122.4480),
    "upper haight": (37.7692, -122.4480),
    "cole valley": (37.7648, -122.4500),
    "ashbury heights": (37.7630, -122.4470),
    "duboce triangle": (37.7675, -122.4320),
    "duboce": (37.7675, -122.4320),
    "potrero hill": (37.7577, -122.3990),
    "potrero": (37.7577, -122.3990),
    "dogpatch": (37.7600, -122.3890),
    "mission bay": (37.7700, -122.3910),
    "china basin": (37.7710, -122.3880),
    "showplace square": (37.7680, -122.4050),
    "design district": (37.7690, -122.4030),
    "rincon hill": (37.7870, -122.3920),
    "yerba buena": (37.7850, -122.4000),
    "transbay": (37.7890, -122.3960),
    "jackson square": (37.7965, -122.4030),
    "fisherman's wharf": (37.8080, -122.4177),
    "fishermans wharf": (37.8080, -122.4177),
    "the wharf": (37.8080, -122.4177),
    "wharf": (37.8080, -122.4177),
    "pier 39": (37.8086, -122.4098),
    "noe valley": (37.7502, -122.4337),
    "bernal heights": (37.7410, -122.4140),
    "bernal": (37.7410, -122.4140),
    "precita park": (37.7470, -122.4110),
    "glen park": (37.7337, -122.4337),
    "diamond heights": (37.7430, -122.4400),
    "twin peaks": (37.7544, -122.4477),
    "corona heights": (37.7640, -122.4400),
    "richmond": (37.7801, -122.4682),
    "inner richmond": (37.7801, -122.4682),
    "outer richmond": (37.7770, -122.4900),
    "richmond / seacliff": (37.7801, -122.4682),
    "seacliff": (37.7850, -122.4900),
    "sunset": (37.7537, -122.4862),
    "inner sunset": (37.7610, -122.4680),
    "outer sunset": (37.7530, -122.4940),
    "sunset / parkside": (37.7537, -122.4862),
    "parkside": (37.7430, -122.4780),
    "golden gate heights": (37.7540, -122.4710),
    "west portal": (37.7400, -122.4660),
    "forest hill": (37.7480, -122.4630),
    "ingleside": (37.7216, -122.4500),
    "ingleside / sfsu / ccsf": (37.7216, -122.4500),
    "oceanview": (37.7140, -122.4570),
    "excelsior": (37.7246, -122.4279),
    "excelsior / outer mission": (37.7246, -122.4279),
    "outer mission": (37.7230, -122.4350),
    "crocker amazon": (37.7120, -122.4390),
    "portola": (37.7264, -122.4100),
    "visitacion valley": (37.7172, -122.4040),
    "bayview": (37.7304, -122.3840),
    "bayview hunters point": (37.7304, -122.3840),
    "hunters point": (37.7260, -122.3710),
    "hunter's point": (37.7260, -122.3710),
    "silver terrace": (37.7320, -122.4000),
    "presidio": (37.7989, -122.4662),
    "presidio heights": (37.7880, -122.4530),
    "laurel heights": (37.7850, -122.4520),
    "anza vista": (37.7800, -122.4430),
    "cathedral hill": (37.7850, -122.4250),
    "polk gulch": (37.7910, -122.4210),
    "fort mason": (37.8070, -122.4310),
    "treasure island": (37.8230, -122.3700),
    "parnassus": (37.7630, -122.4580),
    "miraloma park": (37.7410, -122.4490),
    "stonestown": (37.7280, -122.4770),
    "lakeshore": (37.7240, -122.4900),
    "parkmerced": (37.7180, -122.4810),
    "balboa park": (37.7250, -122.4450),
    "daly city": (37.6879, -122.4702),
    "oakland": (37.8044, -122.2712),
    "oakland east": (37.7900, -122.2200),
    "oakland west": (37.8080, -122.2900),
    "west oakland": (37.8080, -122.2900),
    "oakland north": (37.8340, -122.2650),
    "oakland north / temescal": (37.8340, -122.2650),
    "oakland downtown": (37.8044, -122.2712),
    "downtown oakland": (37.8044, -122.2712),
    "oakland hills": (37.8200, -122.1900),
    "oakland hills / mills": (37.8200, -122.1900),
    "lake merritt": (37.8010, -122.2580),
    "oakland lake merritt / grand": (37.8010, -122.2580),
    "berkeley": (37.8716, -122.2727),
    "emeryville": (37.8313, -122.2853),
    "alameda": (37.7652, -122.2416),
    "hayward": (37.6688, -122.0808),
    "san leandro": (37.7249, -122.1561),
    "richmond ca": (37.9358, -122.3478),
    "san pablo": (37.9621, -122.3455),
}

# SF ZIP → neighborhood key already in AREA_COORDS
ZIP_TO_AREA: dict[str, str] = {
    "94102": "civic center",
    "94103": "soma",
    "94104": "financial district",
    "94105": "transbay",
    "94107": "dogpatch",
    "94108": "chinatown",
    "94109": "nob hill",
    "94110": "mission",
    "94111": "financial district",
    "94112": "ingleside",
    "94114": "castro",
    "94115": "pacific heights",
    "94116": "outer sunset",
    "94117": "haight",
    "94118": "inner richmond",
    "94121": "outer richmond",
    "94122": "inner sunset",
    "94123": "marina",
    "94124": "bayview",
    "94127": "west portal",
    "94129": "presidio",
    "94130": "treasure island",
    "94131": "glen park",
    "94132": "lakeshore",
    "94133": "north beach",
    "94134": "portola",
    "94158": "mission bay",
}

_ZIP_RE = re.compile(r"\b(941\d{2})\b")

_CITY_COORDS: dict[str, tuple[float, float]] = {
    "san francisco": (37.7749, -122.4194),
    "oakland": (37.8044, -122.2712),
    "berkeley": (37.8716, -122.2727),
    "emeryville": (37.8313, -122.2853),
    "alameda": (37.7652, -122.2416),
    "daly city": (37.6879, -122.4702),
    "hayward": (37.6688, -122.0808),
    "san leandro": (37.7249, -122.1561),
    "richmond": (37.9358, -122.3478),
    "san pablo": (37.9621, -122.3455),
    "castro valley": (37.6941, -122.0864),
}

_GENERIC_AREA_LABELS = frozenset(
    {
        "san francisco",
        "city of san francisco",
        "sf",
        "california",
        "ca",
        "oakland",
        "berkeley",
        "emeryville",
        "alameda",
        "daly city",
        "usa",
        "united states",
        "unknown",
        "unknown area",
    }
)

_LARGE_AREA_MARKERS = (
    "sunset",
    "richmond",
    "mission",
    "soma",
    "south of market",
    "bayview",
    "excelsior",
    "ingleside",
    "oakland",
    "berkeley",
)

_SMALL_AREA_MARKERS = (
    "chinatown",
    "hayes valley",
    "jackson square",
    "union square",
    "tenderloin",
    "telegraph hill",
    "duboce",
    "alamo square",
    "rincon hill",
)

_HOOD_KEYS = tuple(
    sorted(
        (name for name in AREA_COORDS if name not in _GENERIC_AREA_LABELS),
        key=len,
        reverse=True,
    )
)


def _normalize_area(text: str) -> str:
    cleaned = re.sub(r"facebook\s*·\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    cleaned = re.sub(
        r",?\s*(?:san francisco|sf)?\s*,?\s*ca(?:lifornia)?\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r",?\s*san francisco\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" ,/-·")
    return cleaned


def area_radius_deg(name: str) -> float:
    """Rough neighborhood radius in degrees (~111km per deg lat)."""
    key = (name or "").strip().lower()
    if not key or key in _GENERIC_AREA_LABELS:
        return 0.012
    if any(marker in key for marker in _SMALL_AREA_MARKERS):
        return 0.0022
    if any(marker in key for marker in _LARGE_AREA_MARKERS):
        return 0.0042
    return 0.0032


def map_areas_payload() -> dict[str, dict[str, float]]:
    """Neighborhood centroids + scatter radius for the map UI."""
    payload: dict[str, dict[str, float]] = {}
    for name, (lat, lng) in AREA_COORDS.items():
        if name in _GENERIC_AREA_LABELS:
            continue
        payload[name] = {
            "lat": lat,
            "lng": lng,
            "radius": round(area_radius_deg(name), 5),
        }
    return payload


def _best_hood_match(text: str) -> tuple[str, tuple[float, float]] | None:
    normalized = _normalize_area(text)
    if not normalized or normalized in _GENERIC_AREA_LABELS:
        return None
    if normalized in AREA_COORDS and normalized not in _GENERIC_AREA_LABELS:
        return normalized, AREA_COORDS[normalized]

    for name in _HOOD_KEYS:
        pattern = rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            return name, AREA_COORDS[name]
        if len(normalized) >= 5 and normalized != name and normalized in name:
            return name, AREA_COORDS[name]
    return None


def _city_match(text: str) -> tuple[str, tuple[float, float]] | None:
    normalized = _normalize_area(text)
    if not normalized:
        blob = (text or "").strip().lower()
    else:
        blob = normalized
    for city, coords in _CITY_COORDS.items():
        if city in blob or blob in city:
            return city, coords
    raw = (text or "").strip().lower()
    for city, coords in _CITY_COORDS.items():
        if city in raw:
            return city, coords
    return None


def resolve_listing_map_point(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return {lat, lng, source, area} for map display.

    Street addresses are geocoded. Neighborhood-only listings use a
    neighborhood centroid (scattered in the UI).
    """
    from lfr.geocode import geocode_street, street_query

    hood_fields = (
        "neighborhood",
        "display_place",
        "display_neighborhood",
    )
    extra_fields = (
        "rental_address",
        "rentalAddress",
        "title",
        "city",
        "zip",
    )
    street_fields = (
        "rental_address",
        "rentalAddress",
        "display_place",
        "display_neighborhood",
        "neighborhood",
        "title",
    )
    for key in street_fields:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        query = street_query(value)
        if not query:
            continue
        coords = geocode_street(query)
        if coords:
            lat, lng = coords
            return {
                "lat": lat,
                "lng": lng,
                "source": "street",
                "area": query,
            }

    for key in hood_fields:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        match = _best_hood_match(value)
        if match:
            name, (lat, lng) = match
            return {
                "lat": lat,
                "lng": lng,
                "source": "neighborhood",
                "area": name,
            }

    for key in extra_fields:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        match = _best_hood_match(value)
        if match:
            name, (lat, lng) = match
            return {
                "lat": lat,
                "lng": lng,
                "source": "neighborhood",
                "area": name,
            }

    zip_blobs = [
        str(row.get(key) or "")
        for key in (*hood_fields, *extra_fields, "displayAddress")
    ]
    zip_blob = " ".join(zip_blobs)
    for zip_code in _ZIP_RE.findall(zip_blob):
        area = ZIP_TO_AREA.get(zip_code)
        if area and area in AREA_COORDS:
            lat, lng = AREA_COORDS[area]
            return {
                "lat": lat,
                "lng": lng,
                "source": "neighborhood",
                "area": area,
            }

    for key in (*hood_fields, *extra_fields):
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        city = _city_match(value)
        if city:
            name, (lat, lng) = city
            return {
                "lat": lat,
                "lng": lng,
                "source": "city",
                "area": name,
            }
    return None


def resolve_listing_coords(row: dict[str, Any]) -> tuple[float, float] | None:
    """Return (lat, lng) for map display."""
    point = resolve_listing_map_point(row)
    if not point:
        return None
    return float(point["lat"]), float(point["lng"])


def sunflower_offset(
    index: int,
    count: int,
    *,
    lat: float,
    radius_deg: float,
) -> tuple[float, float]:
    """Offset from a centroid into an empty ring (deterministic sunflower)."""
    n = max(int(count), 1)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    t = (index + 1) / (n + 1)
    radius = radius_deg * (0.28 + 0.72 * math.sqrt(t))
    theta = index * golden
    dlat = radius * math.cos(theta)
    cos_lat = math.cos(math.radians(lat)) or 1.0
    dlng = (radius * math.sin(theta)) / cos_lat
    return dlat, dlng
