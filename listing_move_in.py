"""Extract move-in wording as written in listing posts."""

from __future__ import annotations

import json
import re
from typing import Any

_MOVE_IN_PHRASE_RE = re.compile(
    r"(?:"
    r"available(?:\s+(?:now|immediately|asap|a\.?s\.?a\.?p\.?))?"
    r"|move[- ]?in(?:\s+date)?(?:\s*(?:is|:))?\s*(?:around|by|on|from)?"
    r"|(?:ready|starting)\s+(?:to\s+move|for\s+move[- ]?in)"
    r")\s*"
    r"(?:"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?"
    r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    r"|(?:now|immediately|asap|flexible)"
    r")?",
    re.IGNORECASE,
)

_AVAILABLE_DATE_RE = re.compile(
    r"available\s+"
    r"(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?|\d{1,2}/\d{1,2}(?:/\d{2,4})?|now|immediately)",
    re.IGNORECASE,
)

_MONTH_DAY_RE = re.compile(
    r"\b((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)\b",
    re.IGNORECASE,
)

_IMMEDIATE_RE = re.compile(
    r"\b(available\s+now|move[- ]?in\s+ready|ready\s+for\s+move[- ]?in|immediate(?:ly)?)\b",
    re.IGNORECASE,
)

_TITLE_DATE_RE = re.compile(
    r"\b((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?)\b",
    re.IGNORECASE,
)

_WEAK_PHRASES = frozenset({
    "available",
    "move-in",
    "move in",
    "move",
    "ready",
})


def _listing_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(row.get(key) or "").strip()
        for key in ("title", "description")
        if row.get(key)
    )


def _clean_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _signal_from_flags(flags_json: str | None) -> str | None:
    if not flags_json:
        return None
    try:
        parsed = json.loads(flags_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    signal = parsed.get("move_in_signal")
    if not signal:
        return None
    signal = str(signal).strip()
    if signal.lower() in ("flexible move-in",):
        return signal
    return signal


def _acceptable_phrase(phrase: str) -> bool:
    cleaned = _clean_phrase(phrase)
    if not cleaned:
        return False
    if cleaned.lower() in _WEAK_PHRASES:
        return False
    if len(cleaned) < 8 and not any(ch.isdigit() for ch in cleaned):
        return False
    return True


def extract_move_in_label(row: dict[str, Any]) -> str | None:
    """Return move-in text from the post, not scoring labels."""
    stored = str(row.get("move_in_date") or "").strip()
    if stored:
        return stored

    title = str(row.get("title") or "")
    blob = _listing_text(row)

    for text in (title, blob):
        if not text:
            continue
        for pattern in (
            _AVAILABLE_DATE_RE,
            _TITLE_DATE_RE,
            _MONTH_DAY_RE,
            _IMMEDIATE_RE,
            _MOVE_IN_PHRASE_RE,
        ):
            match = pattern.search(text)
            if not match:
                continue
            phrase = _clean_phrase(match.group(1) if pattern is _TITLE_DATE_RE else match.group(0))
            if _acceptable_phrase(phrase):
                return phrase

    signal = _signal_from_flags(row.get("flags_json"))
    if signal and _acceptable_phrase(signal):
        return signal
    return None