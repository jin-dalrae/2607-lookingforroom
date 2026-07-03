"""Extract move-in wording as written in listing posts."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

_SORT_UNKNOWN = 999_999_999

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
    r"((?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?|\d{1,2}/\d{1,2}(?:/\d{2,4})?))",
    re.IGNORECASE,
)

_AVAILABLE_IMMEDIATE_RE = re.compile(
    r"\bavailable\s+(now|immediately|asap)\b",
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

_CANONICAL_IMMEDIATE = "Available now"

_IMMEDIATE_LABEL_RE = re.compile(
    r"^(?:"
    r"available\s+now"
    r"|available\s+immediately"
    r"|available\s+asap"
    r"|move[- ]?in\s+ready"
    r"|ready\s+(?:for\s+move[- ]?in|to\s+move)"
    r"|immediate(?:ly)?"
    r"|asap"
    r"|a\.?s\.?a\.?p\.?"
    r")$",
    re.IGNORECASE,
)

_MONTH_NUMBERS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_PARSE_MONTH_DAY_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b",
    re.IGNORECASE,
)

_PARSE_SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")


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


def _normalize_move_in_label(phrase: str) -> str:
    """Collapse immediate wording; drop leading 'available' before dates."""
    cleaned = _clean_phrase(phrase)
    low = cleaned.lower().rstrip("!.:;")
    if _IMMEDIATE_LABEL_RE.fullmatch(low):
        return _CANONICAL_IMMEDIATE
    cleaned = re.sub(r"^available\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^move[- ]?in\s+(?:date\s*)?(?::|is)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_phrase(cleaned)


def extract_move_in_label(row: dict[str, Any]) -> str | None:
    """Return move-in text from the post, not scoring labels."""
    stored = str(row.get("move_in_date") or "").strip()
    if stored:
        return _normalize_move_in_label(stored)

    title = str(row.get("title") or "")
    blob = _listing_text(row)

    for text in (title, blob):
        if not text:
            continue
        for pattern in (
            _AVAILABLE_DATE_RE,
            _AVAILABLE_IMMEDIATE_RE,
            _TITLE_DATE_RE,
            _MONTH_DAY_RE,
            _IMMEDIATE_RE,
            _MOVE_IN_PHRASE_RE,
        ):
            match = pattern.search(text)
            if not match:
                continue
            if pattern is _TITLE_DATE_RE or pattern is _AVAILABLE_DATE_RE:
                phrase = _clean_phrase(match.group(1))
            elif pattern is _AVAILABLE_IMMEDIATE_RE:
                phrase = _clean_phrase(f"available {match.group(1)}")
            else:
                phrase = _clean_phrase(match.group(0))
            if _acceptable_phrase(phrase):
                return _normalize_move_in_label(phrase)

    signal = _signal_from_flags(row.get("flags_json"))
    if signal and _acceptable_phrase(signal):
        return _normalize_move_in_label(signal)
    return _CANONICAL_IMMEDIATE


def _month_token_to_number(token: str) -> int | None:
    return _MONTH_NUMBERS.get(token.lower().strip())


def _infer_move_in_year(month: int, explicit_year: int | None = None) -> int:
    today = date.today()
    if explicit_year is not None:
        if explicit_year < 100:
            return 2000 + explicit_year
        return explicit_year
    if month < today.month - 1:
        return today.year + 1
    return today.year


def _safe_move_in_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_move_in_date_from_label(label: str) -> date | None:
    match = _PARSE_MONTH_DAY_RE.search(label)
    if match:
        month = _month_token_to_number(match.group(1))
        if month is not None:
            day = int(match.group(2))
            explicit_year = int(match.group(3)) if match.group(3) else None
            year = _infer_move_in_year(month, explicit_year)
            return _safe_move_in_date(year, month, day)

    match = _PARSE_SLASH_DATE_RE.search(label)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            explicit_year = int(match.group(3)) if match.group(3) else None
            year = _infer_move_in_year(month, explicit_year)
            return _safe_move_in_date(year, month, day)

    return None


def _yyyymmdd(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def move_in_sort_value(label: str | None) -> int:
    """Numeric helper for table sort: past, then now, then future."""
    if not label:
        return _SORT_UNKNOWN
    cleaned = _clean_phrase(label)
    if not cleaned or cleaned.lower() in _WEAK_PHRASES:
        return _SORT_UNKNOWN
    if cleaned == _CANONICAL_IMMEDIATE or _IMMEDIATE_LABEL_RE.fullmatch(
        cleaned.lower().rstrip("!.:;")
    ):
        return _yyyymmdd(date.today())

    parsed = _parse_move_in_date_from_label(cleaned)
    if parsed is None:
        return _SORT_UNKNOWN

    return _yyyymmdd(parsed)