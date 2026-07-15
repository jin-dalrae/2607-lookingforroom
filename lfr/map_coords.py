"""Resolve rough map coordinates for listings."""

from __future__ import annotations

import re
from typing import Any

# Neighborhood / area centroids for SF + East Bay room search.
AREA_COORDS: dict[str, tuple[float, float]] = {
    "san francisco": (37.7749, -122.4194),
    "city of san francisco": (37.7749, -122.4194),
    "soma": (37.7786, -122.4056),
    "soma / south beach": (37.7786, -122.4056),
    "mission": (37.7599, -122.4148),
    "mission district": (37.7599, -122.4148),
    "castro": (37.7609, -122.4350),
    "castro / upper market": (37.7609, -122.4350),
    "nob hill": (37.7930, -122.4161),
    "lower nob hill": (37.7907, -122.4150),
    "north beach": (37.8061, -122.4103),
    "north beach / telegraph hill": (37.8061, -122.4103),
    "richmond": (37.7801, -122.4682),
    "inner richmond": (37.7801, -122.4682),
    "richmond / seacliff": (37.7801, -122.4682),
    "sunset": (37.7537, -122.4862),
    "sunset / parkside": (37.7537, -122.4862),
    "ingleside": (37.7216, -122.4500),
    "ingleside / sfsu / ccsf": (37.7216, -122.4500),
    "excelsior": (37.7246, -122.4279),
    "excelsior / outer mission": (37.7246, -122.4279),
    "daly city": (37.6879, -122.4702),
    "oakland": (37.8044, -122.2712),
    "oakland east": (37.7900, -122.2200),
    "oakland west": (37.8080, -122.2900),
    "oakland north": (37.8340, -122.2650),
    "oakland north / temescal": (37.8340, -122.2650),
    "oakland downtown": (37.8044, -122.2712),
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


def _normalize_area(text: str) -> str:
    cleaned = re.sub(r"facebook\s*·\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    cleaned = re.sub(r",\s*ca$", "", cleaned).strip()
    return cleaned


def resolve_listing_coords(row: dict[str, Any]) -> tuple[float, float] | None:
    """Return (lat, lng) for map display."""
    candidates: list[str] = []
    for key in ("rental_address", "neighborhood", "city"):
        value = str(row.get(key) or "").strip()
        if value:
            candidates.append(_normalize_area(value))

    place = row.get("display_place") or row.get("neighborhood")
    if place:
        candidates.append(_normalize_area(str(place)))

    for candidate in candidates:
        if candidate in AREA_COORDS:
            return AREA_COORDS[candidate]
        for name, coords in AREA_COORDS.items():
            if name in candidate or candidate in name:
                return coords

    for candidate in candidates:
        for city, coords in _CITY_COORDS.items():
            if city in candidate:
                return coords

    return None