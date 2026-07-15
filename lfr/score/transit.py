"""Transit tier classification and walk-time detection."""

from __future__ import annotations

import re
from typing import Any

from lfr.config import LOCATION_PREFERENCES, TRANSIT_PREFERENCES

from lfr.score.criteria import (
    _BART_TERMS,
    _CALTRAIN_TERMS,
    _MUNI_BUS_TERMS,
    _MUNI_TRAM_CFG,
)
from lfr.score.location_rules import _location_match, _mentions_any


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
