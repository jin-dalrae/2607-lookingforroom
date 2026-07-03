#!/usr/bin/env python3
"""Alert notifications via Telegram or Slack.

Telegram setup
--------------
1. Open Telegram and message @BotFather.
2. Send /newbot, follow prompts, and copy the bot token.
3. Start a chat with your new bot (tap Start).
4. Get your chat_id:
   - Personal chat: message @userinfobot, or visit
     https://api.telegram.org/bot<TOKEN>/getUpdates after messaging your bot.
   - Group chat: add the bot to the group, send a message, then check getUpdates
     for the negative chat_id.
5. Set TELEGRAM_BOT_TOKEN in .env.
6. Either set TELEGRAM_CHAT_ID in .env, or run `python bot.py` and send /start
   to your bot (saves chat_id to telegram_chat.json).

Slack setup
-----------
1. Go to https://api.slack.com/apps → Create New App → From scratch.
2. Enable Incoming Webhooks and add a webhook to your channel.
3. Copy the webhook URL into SLACK_WEBHOOK_URL in .env.

If no credentials are configured, messages are printed (dry-run) instead of sent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

ALERTED_IDS_PATH = Path(__file__).parent / "last_alerted_ids.json"
TELEGRAM_CHAT_JSON_PATH = Path(__file__).parent / "telegram_chat.json"
MIN_SCORE_FOR_ALERT = 80
TOP_N_ALERT = 5

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()


def get_telegram_chat_id() -> str:
    """Return chat_id from .env, or from telegram_chat.json if env is empty."""
    env_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if env_id:
        return env_id
    if not TELEGRAM_CHAT_JSON_PATH.exists():
        return ""
    try:
        data = json.loads(TELEGRAM_CHAT_JSON_PATH.read_text(encoding="utf-8"))
        return str(data.get("chat_id", "")).strip()
    except (json.JSONDecodeError, OSError, TypeError):
        return ""


def save_telegram_chat_id(chat_id: int | str) -> None:
    """Persist chat_id for pipeline alerts (written by bot.py on /start)."""
    payload = {"chat_id": str(chat_id)}
    TELEGRAM_CHAT_JSON_PATH.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_alerted_ids() -> set[str]:
    if not ALERTED_IDS_PATH.exists():
        return set()
    try:
        data = json.loads(ALERTED_IDS_PATH.read_text(encoding="utf-8"))
        return set(data.get("last_alerted_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_alerted_ids(ids: set[str]) -> None:
    payload = {"last_alerted_ids": sorted(ids)}
    ALERTED_IDS_PATH.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _mark_alerted(listing_ids: list[str]) -> None:
    alerted = _load_alerted_ids()
    alerted.update(listing_ids)
    _save_alerted_ids(alerted)


def filter_new_high_score_listings(
    listings: list[dict[str, Any]],
    *,
    min_score: int = MIN_SCORE_FOR_ALERT,
    limit: int = TOP_N_ALERT,
) -> list[dict[str, Any]]:
    """Return top new listings (not yet alerted) with score >= min_score."""
    alerted = _load_alerted_ids()
    fresh: list[dict[str, Any]] = []
    for listing in listings:
        listing_id = listing.get("id")
        score = int(listing.get("score") or 0)
        if not listing_id or score < min_score:
            continue
        if listing_id in alerted:
            continue
        fresh.append(listing)
        if len(fresh) >= limit:
            break
    return fresh


def format_listings_message(
    listings: list[dict[str, Any]],
    *,
    title: str | None = None,
    empty_message: str = "No listings found.",
) -> str:
    """Format ranked listings as a plain-text Telegram-friendly message."""
    if not listings:
        return empty_message

    header = title or f"🏠 SF Room Finder — {len(listings)} listing(s)"
    lines = [header, ""]
    for i, row in enumerate(listings, 1):
        price = f"${row['price']}" if row.get("price") else "N/A"
        listing_title = (row.get("title") or "Untitled")[:60]
        neighborhood = row.get("neighborhood") or "Unknown"
        reasoning = (row.get("reasoning") or "")[:100]
        lines.extend(
            [
                f"{i}. [{row.get('score', 0)}] {listing_title}",
                f"   {price} · {neighborhood}",
                f"   {reasoning}",
                f"   {row.get('url', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _format_digest_message(listings: list[dict[str, Any]]) -> str:
    return format_listings_message(
        listings,
        title=f"🏠 SF Room Finder — {len(listings)} new high-score listing(s)",
    )


def _dry_run(channel: str, message: str) -> None:
    print(f"\n[notify dry-run · {channel}] No credentials configured; would send:\n")
    print(message)
    print()


def _telegram_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and get_telegram_chat_id())


def _slack_configured() -> bool:
    return bool(SLACK_WEBHOOK_URL)


def send_telegram(message: str, chat_id: int | str | None = None) -> bool:
    """Send a plain-text message via Telegram Bot API."""
    target = str(chat_id).strip() if chat_id is not None else get_telegram_chat_id()
    if not TELEGRAM_BOT_TOKEN or not target:
        _dry_run("telegram", message)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": target,
            "text": message[:4096],
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    response.raise_for_status()
    return True


def send_slack(message: str) -> bool:
    """Send a plain-text message via Slack incoming webhook."""
    if not _slack_configured():
        _dry_run("slack", message)
        return False

    response = requests.post(
        SLACK_WEBHOOK_URL,
        json={"text": message},
        timeout=30,
    )
    response.raise_for_status()
    return True


def send_alert(message: str, channel: str = "telegram") -> bool:
    """Dispatch an alert to the chosen channel ('telegram' or 'slack')."""
    if channel == "slack":
        return send_slack(message)
    if channel == "telegram":
        return send_telegram(message)
    raise ValueError(f"Unknown alert channel: {channel!r}")


def send_digest_alert(
    listings: list[dict[str, Any]],
    *,
    channel: str = "telegram",
    min_score: int = MIN_SCORE_FOR_ALERT,
    limit: int = TOP_N_ALERT,
    mark_sent: bool = True,
) -> str:
    """
    Send top N new high-score listings since the last alert.

    Returns one of: "sent", "dry_run", "none".
    """
    new_listings = filter_new_high_score_listings(
        listings,
        min_score=min_score,
        limit=limit,
    )
    if not new_listings:
        return "none"

    message = _format_digest_message(new_listings)
    delivered = send_alert(message, channel=channel)
    if delivered and mark_sent:
        _mark_alerted([str(row["id"]) for row in new_listings])
        return "sent"
    return "dry_run"