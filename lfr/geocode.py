"""Geocode precise SF street addresses (cached Nominatim)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from lfr.paths import PROJECT_ROOT

CACHE_PATH = PROJECT_ROOT / "data" / "geocode-cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "LookingForRoom/1.0 (personal housing search)"
MIN_INTERVAL_SEC = 1.1

_STREET_RE = re.compile(
    r"\b(\d{1,5})\s+[A-Za-z0-9'.-]+(?:\s+[A-Za-z0-9'.-]+){0,4}\s+"
    r"(?:st|street|str|ave|avenue|av|rd|road|blvd|boulevard|dr|drive|"
    r"ln|lane|way|ct|court|pl|place|pkwy|parkway|ter|terrace|cir|circle|"
    r"hwy|alley|walk)\b",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"\s*(?:,\s*)?(?:#\s*\S+|apt\.?\s*\S+|apartment\s*\S+|unit\s*\S+|ste\.?\s*\S+)\b",
    re.IGNORECASE,
)

_SF_LAT = (37.70, 37.84)
_SF_LNG = (-122.53, -122.35)

_last_request = 0.0
_cache: dict[str, Any] | None = None


def looks_like_street_address(text: str) -> bool:
    return bool(_STREET_RE.search(text or ""))


def street_query(text: str) -> str | None:
    """Normalize a listing address into a geocode query, or None."""
    raw = str(text or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r"^(?:zillow|facebook|craigslist)\s*:\s*", "", raw, flags=re.IGNORECASE)
    match = _STREET_RE.search(cleaned)
    if not match:
        return None
    segment = cleaned[match.start() :]
    segment = segment.split("\n", 1)[0]
    segment = _UNIT_RE.sub("", segment)
    segment = re.sub(r"\s+", " ", segment).strip(" ,")
    if "san francisco" not in segment.lower():
        segment = f"{segment}, San Francisco, CA"
    return segment


def _load_cache() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    if CACHE_PATH.is_file():
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _cache = {}
    else:
        _cache = {}
    if not isinstance(_cache, dict):
        _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, indent=2, sort_keys=True), encoding="utf-8")


def _in_sf(lat: float, lng: float) -> bool:
    return _SF_LAT[0] <= lat <= _SF_LAT[1] and _SF_LNG[0] <= lng <= _SF_LNG[1]


def geocode_street(text: str) -> tuple[float, float] | None:
    """Return (lat, lng) for a precise street address in SF, or None."""
    query = street_query(text)
    if not query:
        return None
    key = query.lower()
    cache = _load_cache()
    if key in cache:
        cached = cache[key]
        if not cached:
            return None
        try:
            lat, lng = float(cached[0]), float(cached[1])
        except (TypeError, ValueError, IndexError):
            return None
        return (lat, lng) if _in_sf(lat, lng) else None

    global _last_request
    wait = MIN_INTERVAL_SEC - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        _last_request = time.monotonic()
        if response.status_code >= 400:
            cache[key] = None
            _save_cache()
            return None
        rows = response.json()
    except (requests.RequestException, json.JSONDecodeError, ValueError):
        _last_request = time.monotonic()
        return None

    if not rows:
        cache[key] = None
        _save_cache()
        return None
    try:
        lat = float(rows[0]["lat"])
        lng = float(rows[0]["lon"])
    except (KeyError, TypeError, ValueError):
        cache[key] = None
        _save_cache()
        return None
    if not _in_sf(lat, lng):
        cache[key] = None
        _save_cache()
        return None
    cache[key] = [round(lat, 6), round(lng, 6)]
    _save_cache()
    return lat, lng
