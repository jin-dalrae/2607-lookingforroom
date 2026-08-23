"""Detect multiple rooms available from one house."""

from __future__ import annotations

import re
from typing import Any

_WORD_TO_COUNT = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}

_ROOMS_AVAILABLE_RES = (
    re.compile(
        r"\b(?P<n>two|three|four|five|2|3|4|5)\s+"
        r"(?:private\s+)?(?:rooms?|bedrooms?)\s+"
        r"(?:available|for\s+rent|to\s+rent|open|left)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:available|renting|offering)\s+"
        r"(?:are\s+)?(?P<n>two|three|four|five|2|3|4|5)\s+"
        r"(?:private\s+)?(?:rooms?|bedrooms?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bboth\s+(?:rooms?|bedrooms?)\s+(?:are\s+)?(?:available|for\s+rent|open)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<n>two|three|four|2|3|4)\s+(?:rooms?|bedrooms?)\s+"
        r"in\s+(?:the\s+)?(?:same\s+)?(?:house|apartment|flat|unit|home)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmultiple\s+(?:rooms?|bedrooms?)\s+(?:available|for\s+rent)\b",
        re.IGNORECASE,
    ),
)


def _count_from_match(match: re.Match[str]) -> int:
    if "both" in match.group(0).lower() or "multiple" in match.group(0).lower():
        return 2
    raw = (match.groupdict().get("n") or "").lower()
    if raw.isdigit():
        return int(raw)
    return _WORD_TO_COUNT.get(raw, 0)


def rooms_available_from_text(*parts: str) -> int:
    """Best-effort count of rooms for rent in one house, from listing text."""
    blob = " ".join(str(part or "") for part in parts if part)
    if not blob:
        return 1
    found = 1
    for pattern in _ROOMS_AVAILABLE_RES:
        for match in pattern.finditer(blob):
            count = _count_from_match(match)
            if count > found:
                found = count
    return found


def apply_house_room_counts(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Set roomsInHouse / isMultiRoomHouse after listings are grouped."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in listings:
        groups.setdefault(str(item.get("groupId") or item.get("id")), []).append(item)

    for members in groups.values():
        from_details = max(int(item.get("roomsListed") or 1) for item in members)
        from_group = len(members)
        named_author = any(str(item.get("posterName") or "").strip() for item in members)
        sources: list[str] = []
        if from_details >= 2:
            sources.append("details")
        if from_group >= 2 and named_author:
            sources.append("author")
        total = max(from_details, from_group if named_author else 1)
        if total < 2:
            total = from_details
        for item in members:
            item["roomsInHouse"] = max(from_details, from_group if named_author else from_details)
            item["houseRoomSources"] = sources
            item["isMultiRoomHouse"] = bool(sources)
            item["duplicateCount"] = max(int(item.get("duplicateCount") or 0), from_group - 1)
            if from_group >= 2:
                item["isGrouped"] = True
    return listings
