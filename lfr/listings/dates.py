"""Parse and format listing posted / scraped timestamps."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

_LISTED_RE = re.compile(
    r"listed\s+(?:(\d+)\s+days?\s+ago|yesterday|today|a\s+week\s+ago|(\d+)\s+hours?\s+ago|(\d+)\s+minutes?\s+ago)",
    re.IGNORECASE,
)
_LISTED_RELATIVE_RE = re.compile(
    r"listed\s+"
    r"(?:"
    r"over\s+a\s+week\s+ago"
    r"|a\s+(minute|hour|day|week|month|year)\s+ago"
    r"|(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago"
    r"|yesterday"
    r"|today"
    r"|a\s+week\s+ago"
    r")",
    re.IGNORECASE,
)
_CL_POSTED_RE = re.compile(
    r"posted[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9:+-]+|[A-Za-z]{3,9}\s+\d{1,2})",
    re.IGNORECASE,
)
_ISO_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)
_POSTED_AGO_RE = re.compile(
    r"posted\s+(\d+)\s+(minute|hour|day|week|month)s?\s+ago",
    re.IGNORECASE,
)
_STANDALONE_AGO_RE = re.compile(
    r"\b("
    r"over\s+a\s+week\s+ago"
    r"|a\s+(?:minute|hour|day|week|month|year)\s+ago"
    r"|(?:\d+)\s+(?:minute|hour|day|week|month|year)s?\s+ago"
    r"|yesterday|today|a\s+week\s+ago"
    r")\b",
    re.IGNORECASE,
)

STALE_LISTING_MAX_DAYS = 7

_STALE_PHRASES = frozenset(
    {
        "over a week ago",
        "a year ago",
        "a month ago",
    }
)

_UNIT_TO_DAYS = {
    "minute": 0,
    "hour": 0,
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def listing_text_blob(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(k) or "") for k in ("title", "description"))


def normalize_iso_timestamp(raw: str) -> str | None:
    """Parse CL-style datetime attributes into UTC ISO."""
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}", text):
        text = f"{text[:-5]}{text[-5:-2]}:{text[-2:]}"
    try:
        return _to_iso(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _relative_phrase_from_match(match: re.Match[str]) -> str:
    text = match.group(0).strip()
    return re.sub(r"^listed\s+", "", text, flags=re.IGNORECASE).strip()


def _days_from_relative_phrase(phrase: str) -> int | None:
    low = phrase.lower().strip()
    if low == "today":
        return 0
    if low == "yesterday":
        return 1
    if low == "a week ago":
        return 7
    if low == "over a week ago":
        return 8
    if low in _STALE_PHRASES:
        return _UNIT_TO_DAYS.get(low.split()[-2] if "a " in low else "", 30)

    amount_match = re.match(
        r"(?:a|an|(\d+))\s+(minute|hour|day|week|month|year)s?\s+ago",
        low,
    )
    if amount_match:
        amount = int(amount_match.group(1) or 1)
        unit = amount_match.group(2)
        if unit in ("minute", "hour"):
            return 0
        return amount * _UNIT_TO_DAYS.get(unit, 1)

    amount_match = re.match(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", low)
    if amount_match:
        amount = int(amount_match.group(1))
        unit = amount_match.group(2)
        if unit in ("minute", "hour"):
            return 0
        return amount * _UNIT_TO_DAYS.get(unit, 1)

    return None


def parse_listed_relative(
    text: str,
) -> tuple[int | None, str | None]:
    """Parse Facebook 'Listed … ago' into (days_ago, short display phrase)."""
    if not text:
        return None, None

    match = _LISTED_RELATIVE_RE.search(text)
    if not match:
        return None, None

    phrase = _relative_phrase_from_match(match)
    days = _days_from_relative_phrase(phrase)
    return days, phrase


def listed_age_days(
    text: str,
    *,
    reference: datetime | None = None,
) -> int | None:
    """Best-effort age in days from listing page text."""
    days, _ = parse_listed_relative(text)
    if days is not None:
        return days

    ref = reference or _utcnow()
    listed = _LISTED_RE.search(text)
    if not listed:
        ago = _POSTED_AGO_RE.search(text)
        if not ago:
            return None
        amount = int(ago.group(1))
        unit = ago.group(2).lower()
        if unit == "minute":
            return 0
        if unit == "hour":
            return 0
        if unit == "day":
            return amount
        if unit == "week":
            return amount * 7
        return amount * 30

    if "today" in listed.group(0).lower():
        return 0
    if "yesterday" in listed.group(0).lower():
        return 1
    if "week" in listed.group(0).lower():
        return 7
    if listed.group(1):
        return int(listed.group(1))
    if listed.group(2):
        return 0
    if listed.group(3):
        return 0
    return None


def iso_age_days(iso_value: str | None, *, reference: datetime | None = None) -> int | None:
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ref = reference or _utcnow()
    return max(0, (ref - dt.astimezone(timezone.utc)).days)


def _fb_card_only_listing(row: dict[str, Any]) -> bool:
    """Facebook listing with card-level data only (no reliable detail page scrape)."""
    if str(row.get("source") or "") != "facebook":
        return False
    from lfr.listings.location import extract_rental_location, strip_facebook_page_junk

    raw = str(row.get("description") or "")
    cleaned = strip_facebook_page_junk(raw)
    if extract_rental_location(raw) or extract_rental_location(cleaned):
        return False
    if len(cleaned) >= 120 and "rental location" in raw.lower():
        return False
    return True


def is_stale_listing(
    row: dict[str, Any],
    *,
    max_days: int = STALE_LISTING_MAX_DAYS,
) -> bool:
    """True when Facebook/CL posted age is over max_days (default 1 week)."""
    if _fb_card_only_listing(row):
        title_blob = str(row.get("title") or "")
        rel_days, phrase = parse_listed_relative(title_blob)
        if phrase and phrase.lower() in _STALE_PHRASES:
            return True
        if rel_days is not None and rel_days > max_days:
            return True
        return False

    blob = listing_text_blob(row)
    rel_days, phrase = parse_listed_relative(blob)
    if phrase and phrase.lower() in _STALE_PHRASES:
        return True
    if rel_days is not None and rel_days > max_days:
        return True

    text_days = listed_age_days(blob)
    if text_days is not None and text_days > max_days:
        return True

    posted_at = resolve_posted_at(row)
    if posted_at:
        age = iso_age_days(posted_at)
        if age is not None and age > max_days:
            return True
    return False


def parse_posted_at(
    text: str,
    *,
    reference: datetime | None = None,
) -> str | None:
    """Best-effort posted time from listing page text. Returns UTC ISO string."""
    if not text:
        return None
    ref = reference or _utcnow()

    rel_days, phrase = parse_listed_relative(text)
    if phrase and phrase.lower() in _STALE_PHRASES:
        return None
    if rel_days is not None and rel_days > STALE_LISTING_MAX_DAYS:
        return None

    direct = normalize_iso_timestamp(text)
    if direct:
        return direct

    iso_match = _ISO_RE.search(text)
    if iso_match:
        parsed = normalize_iso_timestamp(iso_match.group(1))
        if parsed:
            return parsed

    cl_match = _CL_POSTED_RE.search(text)
    if cl_match:
        raw = cl_match.group(1).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                parsed = datetime.strptime(raw[:25], fmt)
                return _to_iso(parsed)
            except ValueError:
                continue

    listed = _LISTED_RE.search(text)
    if listed:
        if listed.group(0).lower().find("today") != -1:
            posted = ref
        elif "yesterday" in listed.group(0).lower():
            posted = ref - timedelta(days=1)
        elif "week" in listed.group(0).lower():
            posted = ref - timedelta(days=7)
        elif listed.group(1):
            days = int(listed.group(1))
            if days > STALE_LISTING_MAX_DAYS:
                return None
            posted = ref - timedelta(days=days)
        elif listed.group(2):
            posted = ref - timedelta(hours=int(listed.group(2)))
        elif listed.group(3):
            posted = ref - timedelta(minutes=int(listed.group(3)))
        else:
            posted = None
        if posted is not None:
            return _to_iso(posted)

    if rel_days is not None and rel_days <= STALE_LISTING_MAX_DAYS:
        if rel_days == 0:
            return _to_iso(ref)
        return _to_iso(ref - timedelta(days=rel_days))

    ago = _POSTED_AGO_RE.search(text)
    if ago:
        amount = int(ago.group(1))
        unit = ago.group(2).lower()
        if unit == "minute":
            posted = ref - timedelta(minutes=amount)
        elif unit == "hour":
            posted = ref - timedelta(hours=amount)
        elif unit == "day":
            if amount > STALE_LISTING_MAX_DAYS:
                return None
            posted = ref - timedelta(days=amount)
        elif unit == "week":
            if amount * 7 > STALE_LISTING_MAX_DAYS:
                return None
            posted = ref - timedelta(weeks=amount)
        else:
            return None
        return _to_iso(posted)

    return None


def is_estimated_posted(row: dict[str, Any]) -> bool:
    """True when posted_at is just our first scrape time, not the listing date."""
    posted = row.get("posted_at")
    first_seen = row.get("first_seen")
    if not posted:
        return True
    if first_seen and str(posted) == str(first_seen):
        return True
    return False


def resolve_posted_at(row: dict[str, Any]) -> str | None:
    """Return posted time parsed from the post text, then stored metadata."""
    blob = listing_text_blob(row)
    if extract_posted_phrase(blob):
        parsed = parse_posted_at(blob)
        if parsed:
            return parsed

    stored = row.get("posted_at")
    if stored and not is_estimated_posted(row):
        age = iso_age_days(str(stored))
        if age is not None and age > STALE_LISTING_MAX_DAYS:
            return None
        return str(stored)

    return parse_posted_at(blob)


def fetch_craigslist_posted_at(url: str) -> str | None:
    """Fetch exact posted datetime from a Craigslist listing page."""
    if not url:
        return None
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    try:
        response = requests.get(
            url,
            timeout=12,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        time_el = soup.select_one("time.date.timeago")
        if time_el and time_el.get("datetime"):
            posted_at = normalize_iso_timestamp(time_el["datetime"])
            if posted_at:
                return posted_at
        blob = " ".join(
            info.get_text(" ", strip=True)
            for info in soup.select("p.postinginfo")
        )
        return parse_posted_at(blob)
    except Exception:
        return None


def extract_posted_phrase(text: str) -> str | None:
    """Relative posted wording from listing text, e.g. '4 days ago'."""
    if not text:
        return None

    _, phrase = parse_listed_relative(text)
    if phrase:
        return phrase

    listed = _LISTED_RE.search(text)
    if listed:
        raw = listed.group(0).strip()
        return re.sub(r"^listed\s+", "", raw, flags=re.IGNORECASE).strip()

    match = _STANDALONE_AGO_RE.search(text)
    if match:
        return match.group(1).strip()

    posted_ago = _POSTED_AGO_RE.search(text)
    if posted_ago:
        return posted_ago.group(0).strip()

    return None


def format_posted_age_label(iso_value: str | None) -> str:
    """Turn an exact posted timestamp into FB-style relative wording."""
    if not iso_value:
        return "Unknown"
    age = iso_age_days(iso_value)
    if age is None:
        return format_exact_timestamp(iso_value)
    if age == 0:
        return "today"
    if age == 1:
        return "yesterday"
    if age == 7:
        return "a week ago"
    return f"{age} days ago"


def format_exact_timestamp(iso_value: str | None) -> str:
    """Exact local date + time for table display."""
    if not iso_value:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
    except ValueError:
        return str(iso_value)[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime("%b %-d, %Y %-I:%M %p")


def posted_display_label(row: dict[str, Any]) -> str:
    """Human posted label — use relative wording from the post when present."""
    blob = listing_text_blob(row)
    phrase = extract_posted_phrase(blob)
    if phrase:
        return phrase

    posted_at = resolve_posted_at(row)
    if not posted_at:
        stored = row.get("posted_at")
        if stored and not is_estimated_posted({**row, "posted_at": stored}):
            posted_at = str(stored)
    if posted_at:
        return format_posted_age_label(posted_at)

    return "Unknown"


def posted_label(
    iso_value: str | None,
    *,
    estimated: bool = False,
    row: dict[str, Any] | None = None,
) -> str:
    if row is not None:
        return posted_display_label(row)
    if not iso_value or estimated:
        return "Unknown" if not iso_value else f"{format_exact_timestamp(iso_value)} (est.)"
    return format_exact_timestamp(iso_value)


def format_timestamp_label(iso_value: str | None) -> str:
    if not iso_value:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
    except ValueError:
        return str(iso_value)[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    now = _utcnow().astimezone(local.tzinfo)
    delta = now - local
    days = delta.days
    if days < 0:
        return local.strftime("%b %-d")
    if days == 0:
        hours = int(delta.total_seconds() // 3600)
        if hours <= 0:
            return "today"
        return f"{hours}h ago"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days}d ago"
    return "over a week ago"