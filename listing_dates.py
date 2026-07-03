"""Parse and format listing posted / scraped timestamps."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

_LISTED_RE = re.compile(
    r"listed\s+(?:(\d+)\s+days?\s+ago|yesterday|today|a\s+week\s+ago|(\d+)\s+hours?\s+ago)",
    re.IGNORECASE,
)
_CL_POSTED_RE = re.compile(
    r"posted[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9:+-]+|[A-Za-z]{3,9}\s+\d{1,2})",
    re.IGNORECASE,
)
_ISO_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_posted_at(
    text: str,
    *,
    reference: datetime | None = None,
) -> str | None:
    """Best-effort posted time from listing page text. Returns UTC ISO string."""
    if not text:
        return None
    ref = reference or _utcnow()

    iso_match = _ISO_RE.search(text)
    if iso_match:
        raw = iso_match.group(1).replace("Z", "+00:00")
        try:
            return _to_iso(datetime.fromisoformat(raw))
        except ValueError:
            pass

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
            posted = ref - timedelta(days=int(listed.group(1)))
        elif listed.group(2):
            posted = ref - timedelta(hours=int(listed.group(2)))
        else:
            posted = None
        if posted is not None:
            return _to_iso(posted)

    return None


def resolve_posted_at(row: dict[str, Any]) -> str | None:
    """Return stored posted_at or parse from description as fallback."""
    stored = row.get("posted_at")
    if stored:
        return str(stored)
    blob = " ".join(
        str(row.get(k) or "") for k in ("description", "title")
    )
    return parse_posted_at(blob)


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
    return local.strftime("%b %-d")