"""Outreach channel labels for email, iMessage, Craigslist, Facebook, etc."""

from __future__ import annotations

from typing import Any

OUTREACH_CHANNELS = frozenset(
    {"craigslist", "email", "imessage", "phone", "facebook", "other"}
)

CHANNEL_LABELS = {
    "craigslist": "Craigslist email",
    "email": "Gmail",
    "imessage": "iMessage",
    "phone": "Phone call",
    "facebook": "Facebook",
    "other": "Other",
}

CHANNEL_ICONS = {
    "craigslist": "✉️",
    "email": "✉️",
    "imessage": "💬",
    "phone": "📞",
    "facebook": "📘",
    "other": "•",
}


def normalize_channel(raw: str | None, *, default: str = "craigslist") -> str:
    ch = (raw or default).strip().lower()
    if ch in ("sms", "text", "messages", "imsg"):
        return "imessage"
    return ch if ch in OUTREACH_CHANNELS else default


def channel_label(raw: str | None) -> str:
    ch = normalize_channel(raw, default="other")
    return CHANNEL_LABELS.get(ch, ch)


def channel_icon(raw: str | None) -> str:
    ch = normalize_channel(raw, default="other")
    return CHANNEL_ICONS.get(ch, "•")


def is_facebook_listing(listing: dict[str, Any] | None) -> bool:
    if not listing:
        return False
    source = (listing.get("source") or "").strip().lower()
    url = (listing.get("url") or "").lower()
    listing_id = (listing.get("id") or listing.get("listing_id") or "").lower()
    return (
        source == "facebook"
        or ("facebook.com" in url and "/marketplace/item/" in url)
        or listing_id.startswith("fb-")
    )


def default_channel_for_listing(listing: dict[str, Any] | None) -> str:
    if is_facebook_listing(listing):
        return "facebook"
    url = (listing.get("url") or "").lower() if listing else ""
    if "craigslist.org" in url:
        return "craigslist"
    return "craigslist"


def parse_channel_args(args: list[str], *, default: str = "craigslist") -> tuple[str, list[str]]:
    """Extract optional channel from CLI/Telegram args (first or last token)."""
    remaining = list(args)
    channel = default
    if remaining and remaining[0].lower() in OUTREACH_CHANNELS | {"sms", "text", "imessage"}:
        channel = normalize_channel(remaining.pop(0), default=default)
    elif remaining and remaining[-1].lower() in OUTREACH_CHANNELS | {"sms", "text", "imessage"}:
        channel = normalize_channel(remaining.pop(), default=default)
    return channel, remaining