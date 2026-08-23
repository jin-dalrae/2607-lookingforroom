"""Extract move-in wording as written in listing posts."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from lfr.config import SEARCH_CRITERIA

_SORT_UNKNOWN = 999_999_999

_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)

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

_AVAILABILITY_BLOCK_RE = re.compile(
    r"availability\s*\n\s*([^\n]+)",
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

_LEGACY_IMMEDIATE_LABELS = frozenset({
    "available now",
    "available immediately",
    "available asap",
    "move-in ready",
    "immediate",
    "immediately",
    "asap",
})

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

_PARSE_DISPLAY_MONTH_DAY_RE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?$",
    re.IGNORECASE,
)

_BOILERPLATE_MOVE_IN_RE = re.compile(
    r"^(?:"
    r"move[- ]?in\s*:?"
    r"|ready\s+for\s+move[- ]?in"
    r"|move[- ]?in\s+ready"
    r")$",
    re.IGNORECASE,
)

_PARSE_SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FRACTION_SIGNAL_RE = re.compile(r"^\d{1,2}/\d{1,2}$")

_MOVE_IN_AFTER_DATE_RE = re.compile(
    r"\b(?:available|move[- ]?in|ready|starting|open(?:ing)?|not\s+available\s+until)\s+after\s+"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b",
    re.IGNORECASE,
)

def _move_in_after_cutoff():
    return SEARCH_CRITERIA.get("move_in_hard_reject_after")


def _move_in_window_end():
    return SEARCH_CRITERIA.get("move_in_end")


def _parse_after_move_in_match(match: re.Match[str]) -> date | None:
    month = _month_token_to_number(match.group(1))
    if month is None:
        return None
    day = int(match.group(2))
    explicit_year = int(match.group(3)) if match.group(3) else None
    year = _infer_move_in_year(month, day, explicit_year)
    return _safe_move_in_date(year, month, day)


def move_in_after_cutoff_hit(text: str) -> tuple[bool, str | None]:
    """True when post says available after the user's hard-reject cutoff."""
    cutoff = _move_in_after_cutoff()
    window_end = _move_in_window_end()
    if cutoff is None and window_end is None:
        return False, None
    if not SEARCH_CRITERIA.get("require_move_in_window", True) and cutoff is None:
        return False, None
    blob = text or ""
    for match in _MOVE_IN_AFTER_DATE_RE.finditer(blob):
        stated = _parse_after_move_in_match(match)
        if stated is None:
            continue
        effective = stated + timedelta(days=1)
        too_late = False
        if cutoff is not None and stated >= cutoff:
            too_late = True
        if window_end is not None and effective > window_end:
            too_late = True
        if too_late:
            signal = _clean_phrase(match.group(0))
            return True, signal
    return False, None


def listing_has_move_in_after_cutoff(row: dict[str, Any]) -> bool:
    """Hard reject when listing text says move-in after the Aug 19 cutoff."""
    hit, _ = move_in_after_cutoff_hit(_listing_text(row))
    return hit


def _listing_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(row.get(key) or "").strip()
        for key in ("title", "description")
        if row.get(key)
    )


def _clean_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _ordinal_suffix(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_move_in_date_label(value: date) -> str:
    """Human label like 'august 1st' for a calendar date."""
    return f"{_MONTH_NAMES[value.month - 1]} {value.day}{_ordinal_suffix(value.day)}"


def _phrase_key(text: str) -> str:
    return _clean_phrase(text).lower().rstrip("!.:;")


def is_boilerplate_move_in_phrase(text: str) -> bool:
    """True for fee/deposit wording — not a calendar move-in date."""
    key = _phrase_key(text)
    if not key:
        return True
    if key in _WEAK_PHRASES or key in _LEGACY_IMMEDIATE_LABELS:
        return True
    return bool(_BOILERPLATE_MOVE_IN_RE.fullmatch(key))


def _move_in_match_is_boilerplate(text: str, match: re.Match[str]) -> bool:
    start = match.start()
    prefix = text[max(0, start - 24):start].lower()
    if re.search(r"(?:cost|fee|deposit|security|ready)\s+(?:for\s+)?to\s*$", prefix):
        return True
    if re.search(r"\bcost\s+to\s*$", prefix):
        return True
    return is_boilerplate_move_in_phrase(match.group(0))


def _move_in_phrase_has_date(phrase: str) -> bool:
    normalized = _normalize_move_in_label(phrase)
    if is_boilerplate_move_in_phrase(normalized):
        return False
    return _parse_move_in_date_from_label(normalized) is not None


def is_utility_fraction(text: str, match: re.Match[str]) -> bool:
    """True when a/b is a bill split (e.g. '1/3 of PG&E'), not a move-in date."""
    start, end = match.span()
    snippet = text[max(0, start - 40): min(len(text), end + 40)].lower()
    tail = text[end: min(len(text), end + 12)].lower()

    if re.search(
        r"\d{1,2}/\d{1,2}\s+of\s+(?:the\s+)?(?:pg&?e|utilities|util|rent|bills|garbage|water|wifi|internet|electric)",
        snippet,
    ):
        return True
    if re.search(r"\b(?:plus|split|pay|each|share)\s+(?:\d{1,2}/)?\d{1,2}/\d{1,2}\b", snippet):
        return True
    if re.search(r"\d{1,2}/\d{1,2}(?:rd|th)?\s+each\b", snippet):
        return True
    if tail.lstrip().startswith("of "):
        return True

    numerator = int(match.group(1))
    denominator = int(match.group(2))
    if (
        not match.group(3)
        and numerator <= 3
        and denominator <= 4
        and numerator < denominator
    ):
        return True

    return False


def _is_fraction_signal(text: str) -> bool:
    return bool(_FRACTION_SIGNAL_RE.fullmatch(_clean_phrase(text)))


def _parse_iso_timestamp(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if _ISO_DATE_RE.match(raw):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc).date()
    except ValueError:
        return None


def scrape_date_from_row(row: dict[str, Any]) -> date | None:
    """First day we saw the listing — used when the post omits a move-in date."""
    for key in ("last_seen", "first_seen"):
        parsed = _parse_iso_timestamp(str(row.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


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
    if _is_fraction_signal(signal) or is_boilerplate_move_in_phrase(signal):
        return None
    return signal


def _acceptable_phrase(phrase: str) -> bool:
    cleaned = _clean_phrase(phrase)
    if not cleaned or is_boilerplate_move_in_phrase(cleaned):
        return False
    if _is_fraction_signal(cleaned):
        return False
    if not any(ch.isdigit() for ch in cleaned):
        return False
    return True


def _normalize_move_in_label(phrase: str) -> str:
    """Collapse immediate wording; drop leading 'available' before dates."""
    cleaned = _clean_phrase(phrase)
    low = cleaned.lower().rstrip("!.:;")
    if low in _LEGACY_IMMEDIATE_LABELS or _IMMEDIATE_LABEL_RE.fullmatch(low):
        return cleaned
    cleaned = re.sub(r"^available\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^move[- ]?in\s+(?:date\s*)?(?::|is)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_phrase(cleaned)


def _slash_date_in_move_in_context(text: str, match: re.Match[str]) -> bool:
    if is_utility_fraction(text, match):
        return False
    start = match.start()
    prefix = text[max(0, start - 24):start].lower()
    return bool(
        re.search(r"(?:available|move[- ]?in|starting|ready|from|on|by)\s*$", prefix)
        or match.group(3)
    )


def extract_explicit_move_in_label(row: dict[str, Any]) -> str | None:
    """Return move-in text parsed from the post — no scrape-date fallback."""
    title = str(row.get("title") or "")
    blob = _listing_text(row)

    avail = _AVAILABILITY_BLOCK_RE.search(blob)
    if avail:
        phrase = _clean_phrase(avail.group(1))
        if phrase and not is_boilerplate_move_in_phrase(phrase):
            normalized = _normalize_move_in_label(phrase)
            if _IMMEDIATE_LABEL_RE.fullmatch(normalized.lower().rstrip("!.:;")):
                return normalized
            if _acceptable_phrase(normalized) or _parse_move_in_date_from_label(normalized):
                return normalized

    for text in (title, blob):
        if not text:
            continue
        for pattern in (
            _AVAILABLE_DATE_RE,
            _AVAILABLE_IMMEDIATE_RE,
            _TITLE_DATE_RE,
            _MONTH_DAY_RE,
            _MOVE_IN_PHRASE_RE,
        ):
            match = pattern.search(text)
            if not match:
                continue
            if pattern is _MOVE_IN_PHRASE_RE:
                if _move_in_match_is_boilerplate(text, match):
                    continue
                phrase = _clean_phrase(match.group(0))
                if not _move_in_phrase_has_date(phrase):
                    continue
            elif pattern is _TITLE_DATE_RE or pattern is _AVAILABLE_DATE_RE:
                phrase = _clean_phrase(match.group(1))
                if pattern is _AVAILABLE_DATE_RE:
                    slash = _PARSE_SLASH_DATE_RE.search(phrase)
                    if slash and is_utility_fraction(text, slash):
                        continue
            elif pattern is _AVAILABLE_IMMEDIATE_RE:
                continue
            else:
                phrase = _clean_phrase(match.group(0))
            if not _acceptable_phrase(phrase):
                continue
            normalized = _normalize_move_in_label(phrase)
            if _is_fraction_signal(normalized):
                continue
            if is_boilerplate_move_in_phrase(normalized):
                continue
            return normalized

        for slash in _PARSE_SLASH_DATE_RE.finditer(text):
            if not _slash_date_in_move_in_context(text, slash):
                continue
            phrase = _clean_phrase(slash.group(0))
            if _acceptable_phrase(phrase):
                return phrase

    signal = _signal_from_flags(row.get("flags_json"))
    if signal and _acceptable_phrase(signal):
        normalized = _normalize_move_in_label(signal)
        if normalized.lower() not in _LEGACY_IMMEDIATE_LABELS and not _is_fraction_signal(normalized):
            return normalized
    return None


def default_move_in_label(row: dict[str, Any]) -> str:
    """Scrape-day label when the post does not specify a move-in date."""
    scraped = scrape_date_from_row(row) or date.today()
    return format_move_in_date_label(scraped)


def _label_from_storage(stored: str, row: dict[str, Any]) -> str | None:
    raw = stored.strip()
    if not raw:
        return None
    if _ISO_DATE_RE.match(raw):
        try:
            return format_move_in_date_label(date.fromisoformat(raw))
        except ValueError:
            return None
    if is_boilerplate_move_in_phrase(raw):
        return None
    if _is_fraction_signal(raw):
        return None
    explicit = _normalize_move_in_label(raw)
    parsed = _parse_move_in_date_from_label(explicit)
    if parsed is not None:
        return format_move_in_date_label(parsed)
    return explicit


def extract_move_in_label(row: dict[str, Any]) -> str:
    """Return move-in label for display."""
    stored = str(row.get("move_in_date") or "").strip()
    if stored:
        label = _label_from_storage(stored, row)
        if label:
            return label

    explicit = extract_explicit_move_in_label(row)
    if explicit:
        parsed = _parse_move_in_date_from_label(explicit)
        if parsed is not None:
            return format_move_in_date_label(parsed)
        if not is_boilerplate_move_in_phrase(explicit):
            return explicit.lower()

    return default_move_in_label(row)


def resolve_move_in_date_storage(row: dict[str, Any]) -> str:
    """Persistable move-in value — ISO date, or explicit text when unparsed."""
    stored = str(row.get("move_in_date") or "").strip()
    if stored and _ISO_DATE_RE.match(stored) and not _is_fraction_signal(stored):
        if stored.lower() not in _LEGACY_IMMEDIATE_LABELS:
            return stored

    explicit = extract_explicit_move_in_label(row)
    if explicit:
        parsed = _parse_move_in_date_from_label(explicit)
        if parsed is not None:
            return parsed.isoformat()
        if not is_boilerplate_move_in_phrase(explicit) and not _is_fraction_signal(explicit):
            return explicit

    scraped = scrape_date_from_row(row) or date.today()
    return scraped.isoformat()


def should_refresh_move_in_date(row: dict[str, Any]) -> bool:
    stored = str(row.get("move_in_date") or "").strip()
    if not stored:
        return True
    if _ISO_DATE_RE.match(stored):
        return False
    if is_boilerplate_move_in_phrase(stored):
        return True
    if _is_fraction_signal(stored):
        return True
    if stored.lower() in _LEGACY_IMMEDIATE_LABELS:
        return True
    if _parse_move_in_date_from_label(stored) is None:
        return True
    return False


def _month_token_to_number(token: str) -> int | None:
    return _MONTH_NUMBERS.get(token.lower().strip())


def _infer_move_in_year(month: int, day: int, explicit_year: int | None = None) -> int:
    """Pick the year closest to today when the post omits a year."""
    today = date.today()
    if explicit_year is not None:
        if explicit_year < 100:
            return 2000 + explicit_year
        return explicit_year

    candidates: list[date] = []
    for year in (today.year - 1, today.year, today.year + 1):
        parsed = _safe_move_in_date(year, month, day)
        if parsed:
            candidates.append(parsed)

    if not candidates:
        return today.year

    return min(candidates, key=lambda d: abs((d - today).days)).year


def _safe_move_in_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_move_in_date_from_label(label: str) -> date | None:
    cleaned = _clean_phrase(label)
    if not cleaned:
        return None

    display = _PARSE_DISPLAY_MONTH_DAY_RE.match(cleaned)
    if display:
        month = _month_token_to_number(display.group(1))
        if month is not None:
            day = int(display.group(2))
            year = _infer_move_in_year(month, day)
            return _safe_move_in_date(year, month, day)

    if _ISO_DATE_RE.match(cleaned):
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            return None

    match = _PARSE_MONTH_DAY_RE.search(cleaned)
    if match:
        month = _month_token_to_number(match.group(1))
        if month is not None:
            day = int(match.group(2))
            explicit_year = int(match.group(3)) if match.group(3) else None
            year = _infer_move_in_year(month, day, explicit_year)
            return _safe_move_in_date(year, month, day)

    match = _PARSE_SLASH_DATE_RE.search(cleaned)
    if match and not is_utility_fraction(cleaned, match):
        month = int(match.group(1))
        day = int(match.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            explicit_year = int(match.group(3)) if match.group(3) else None
            year = _infer_move_in_year(month, day, explicit_year)
            return _safe_move_in_date(year, month, day)

    return None


def _yyyymmdd(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def move_in_sort_value(label: str | None) -> int:
    """Numeric helper for table sort: past, then now, then future."""
    if not label:
        return _SORT_UNKNOWN
    cleaned = _clean_phrase(label)
    if not cleaned or is_boilerplate_move_in_phrase(cleaned):
        return _SORT_UNKNOWN
    if cleaned.lower() in _LEGACY_IMMEDIATE_LABELS or _IMMEDIATE_LABEL_RE.fullmatch(
        cleaned.lower().rstrip("!.:;")
    ):
        return _yyyymmdd(date.today())

    parsed = _parse_move_in_date_from_label(cleaned)
    if parsed is None:
        return _SORT_UNKNOWN

    return _yyyymmdd(parsed)