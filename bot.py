#!/usr/bin/env python3
"""Interactive Telegram bot for SF/Oakland room finder.

Long-polling bot using requests only. Start with:

    python bot.py

Users must open the bot link and tap Start (/start) once so chat_id is saved
for replies and pipeline alerts.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from typing import Any

import requests
from dotenv import load_dotenv

import notify
from channels import channel_icon, channel_label, parse_channel_args
from apply import (
    create_application,
    format_apply_message,
    format_prep_message,
    load_profile,
)
from db import (
    count_listings,
    get_application_stats,
    get_connection,
    get_first_unapplied_ranked_listing,
    get_last_draft_application,
    get_last_sent_application,
    get_listing_by_url,
    get_ranked_listing_at_position,
    get_ranked_listings,
    get_unapplied_ranked_listings,
    init_pipeline_tables,
    list_applications,
    mark_all_drafts_sent,
    mark_application_sent,
    mark_listing_unavailable,
    update_application_channel,
    update_application_status,
    _listing_with_score,
)
from rank import (
    _move_in_display,
    _parse_flags_payload,
    _rent_period_display,
    _size_display,
    _transit_tier,
    _transit_label,
)
from run import run_pipeline
import filter as listing_filter
import mail_monitor
import rank as rank_module
import send_mail

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "Rae_house_bot").strip()
BOT_LINK = f"https://t.me/{TELEGRAM_BOT_USERNAME}"
POLL_TIMEOUT_SEC = 30
TRANSIT_POOL_LIMIT = 100

WELCOME_TEXT = (
    "SF/Oakland room finder. Commands: /top /apply /send /batch /sent /apps /mail /gmail /run /help"
)

HELP_TEXT = """SF/Oakland room finder — commands:

/top — top 5 matches (late Jul–Aug 18, ≤$1300)
/august — same as /top
/tram — top 5 near Muni Metro/tram
/caltrain — top 5 Caltrain-adjacent
/apply — draft message for next listing to apply to
/apply 2 — draft for 2nd ranked listing
/send — SMTP email if listing has a direct address (rare on Craigslist)
/send 3 — try ranked #3; otherwise open URL + paste /apply draft
/batch — batch drafts + link to batch_apply.html
/sentall — mark all drafts as sent (after batch apply)
/sentall imessage — mark all drafts as sent via iMessage
/sent 3 — mark 3rd ranked listing as sent
/sent imessage 3 — mark #3 as sent via iMessage
/sent imessage <url> — mark one listing as sent via iMessage
/rechannel imessage 3 — fix channel on an already-tracked send
/applied — mark last draft as sent (alias)
/replied — mark last sent as replied (landlord responded)
/mail — check Gmail inbox for landlord replies (one scan)
/mail loop — how to run background polling every 5 min
/gmail status — OAuth vs App Password vs not configured
/gmail auth — one-time OAuth setup instructions
/apps — pipeline + recent application statuses
/prep — tour questions for last drafted listing
/prep 2 — tour questions for 2nd ranked listing
/dead <url> — mark listing unavailable (rented/gone)
/run — scout + filter + rank (~3 min), then digest summary
/run fb — same pipeline + Facebook Marketplace (if logged in)
/fb — Facebook login/poll help
/fb poll — poll Marketplace (needs login on your Mac first)
/comm — follow-up page (listing-mails-communication)
/status — listing count and last poll time
/help — this message"""


def _api_base() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def reply(chat_id: int | str, message: str) -> bool:
    """Send a reply to a Telegram chat."""
    try:
        return notify.send_telegram(message, chat_id=chat_id)
    except requests.RequestException as exc:
        print(f"telegram send failed: {exc}", file=sys.stderr)
        return False


def _format_listing_rows(
    listings: list[dict[str, Any]],
    *,
    title: str,
    empty_message: str,
) -> str:
    if not listings:
        return empty_message

    lines = [title, ""]
    for i, row in enumerate(listings, 1):
        price = f"${row['price']}" if row.get("price") else "N/A"
        listing_title = (row.get("title") or "Untitled")[:55]
        neighborhood = row.get("neighborhood") or "Unknown"
        reasoning = (row.get("reasoning") or "")[:90]
        transit_label = _transit_label(row)
        transit = f" · {transit_label}" if transit_label else ""
        _, _, _, rent_period, short_term_reject = _parse_flags_payload(row.get("flags_json"))
        period_warning = ""
        period_label = _rent_period_display(rent_period)
        if short_term_reject or rent_period in ("weekly", "daily"):
            period_warning = f" ⚠️ {period_label or 'short-term'} — not monthly"
        elif period_label:
            period_warning = f" ({period_label})"
        size_label = _size_display(row.get("flags_json"))
        size_line = f"   {size_label}" if size_label else ""
        move_in_label = _move_in_display(row.get("flags_json"))
        move_in_line = f"   {move_in_label}" if move_in_label else ""
        block = [
            f"{i}. {listing_title}",
            f"   {price} · {neighborhood}{transit}{period_warning}",
        ]
        if size_line:
            block.append(size_line)
        if move_in_line:
            block.append(move_in_line)
        block.extend(
            [
                f"   {reasoning}",
                f"   {row.get('url', '')}",
                "",
            ]
        )
        lines.extend(block)
    return "\n".join(lines).rstrip()


def _top_listings(limit: int = 5) -> list[dict[str, Any]]:
    return get_ranked_listings(limit=limit, exclude_scams=True)


def _listings_by_transit_tier(tier: str, limit: int = 5) -> list[dict[str, Any]]:
    pool = get_ranked_listings(limit=TRANSIT_POOL_LIMIT, exclude_scams=True)
    filtered = [row for row in pool if _transit_tier(row) == tier]
    return filtered[:limit]


def _status_message() -> str:
    init_pipeline_tables()
    total = count_listings()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(last_seen) AS last_poll FROM listings"
        ).fetchone()
        scored_row = conn.execute("SELECT COUNT(*) AS n FROM scores").fetchone()
    last_poll = (row["last_poll"] if row else None) or "never"
    scored = int(scored_row["n"]) if scored_row else 0
    return (
        f"Status\n"
        f"Listings in DB: {total}\n"
        f"Scored listings: {scored}\n"
        f"Last poll (max last_seen): {last_poll}"
    )


def _pipeline_summary(results: dict[str, int]) -> str:
    top = _top_listings(limit=5)
    lines = [
        "Pipeline complete.",
        f"Scout: {results.get('scout', 0)} new",
        f"Filter: {results.get('filter', 0)} scored",
        f"Rank: {results.get('rank', 0)} in digest",
        "",
    ]
    if top:
        lines.append(_format_listing_rows(
            top,
            title="Top 5 after refresh",
            empty_message="",
        ))
    else:
        lines.append("No scored listings yet.")
    return "\n".join(lines).rstrip()


def _command_args(text: str) -> tuple[str, list[str]]:
    parts = (text or "").strip().split()
    if not parts:
        return "", []
    command = parts[0].lower().split("@")[0]
    return command, parts[1:]


def _format_gmail_status_message() -> str:
    import gmail_auth

    status = gmail_auth.auth_status()
    mode = mail_monitor.gmail_auth_mode()
    address = mail_monitor._default_gmail_address() or "(not set)"

    mode_lines = {
        "oauth": "Active: Gmail API (OAuth token valid)",
        "app_password": "Active: IMAP/SMTP (App Password)",
        "none": "Not configured — no OAuth token or App Password",
    }

    lines = [
        "Gmail auth status",
        f"Address: {address}",
        mode_lines.get(mode, mode),
        "",
        f"OAuth client configured: {'yes' if status['oauth_configured'] else 'no'}",
        f"OAuth token valid: {'yes' if status['token_valid'] else 'no'}",
        f"App Password set: {'yes' if mail_monitor._app_password_configured() else 'no'}",
    ]

    if mode == "none":
        lines.extend(
            [
                "",
                "Setup options:",
                "• OAuth (recommended): /gmail auth",
                "• App Password: GMAIL_ADDRESS + GMAIL_APP_PASSWORD in .env",
            ]
        )
    elif mode == "oauth":
        lines.append("")
        lines.append("mail_monitor + send_mail use Gmail API.")
    else:
        lines.append("")
        lines.append("mail_monitor uses IMAP; send_mail uses SMTP.")

    return "\n".join(lines)


def _format_gmail_auth_instructions() -> str:
    return (
        "Gmail OAuth setup (one-time)\n\n"
        "1. GCP Console → project 267981036962\n"
        "   • Enable Gmail API\n"
        "   • OAuth consent screen (add your Gmail as test user if External)\n"
        "   • Credentials → OAuth 2.0 Client → Desktop app\n\n"
        "2. Add to .env:\n"
        "   GMAIL_OAUTH_CLIENT_ID=...\n"
        "   GMAIL_OAUTH_CLIENT_SECRET=...  (from Credentials page)\n"
        "   GMAIL_ADDRESS=your@gmail.com\n\n"
        "3. On this machine, run:\n"
        "   python oauth_setup.py\n\n"
        "4. Verify: /gmail status\n\n"
        "Fallback: App Password (GMAIL_APP_PASSWORD) still works without OAuth."
    )


def _format_apps_message() -> str:
    stats = get_application_stats()
    apps = list_applications(limit=20)
    if not apps:
        return "No applications yet. Try /apply to draft your first message."

    status_icons = {
        "draft": "📝",
        "sent": "✉️",
        "replied": "💬",
        "toured": "🏠",
        "rejected": "❌",
        "accepted": "✅",
    }
    lines = [
        "Application pipeline",
        f"sent {stats.get('sent', 0)} · replied {stats.get('replied', 0)} · "
        f"toured {stats.get('toured', 0)} · rejected {stats.get('rejected', 0)} · "
        f"awaiting fresh {stats.get('awaiting_fresh', 0)}",
        f"drafts not sent: {stats.get('draft', 0)}",
        "",
        "Recent",
    ]
    for i, app in enumerate(apps, 1):
        icon = status_icons.get(app["status"], "•")
        title = (app.get("title") or "Untitled")[:45]
        price = f"${app['price']}" if app.get("price") else "N/A"
        score = app.get("score")
        score_bit = f" [{score}]" if score is not None else ""
        channel = app.get("channel") or ""
        channel_bit = (
            f" {channel_icon(channel)} {channel_label(channel)}"
            if channel
            else ""
        )
        lines.append(
            f"{i}. {icon} {app['status']}{channel_bit}{score_bit} — {title}\n"
            f"   {price} · {app.get('neighborhood') or 'Unknown'}\n"
            f"   {app.get('url', '')}"
        )
    return "\n".join(lines)


def _resolve_listing_ref(ref: str) -> dict | None:
    ref = ref.strip()
    if not ref:
        return None
    if ref.startswith("http"):
        listing = get_listing_by_url(ref)
        if listing is None:
            path = ref.rstrip("/").split("/")[-1]
            from db import get_listing_by_id

            listing = get_listing_by_id(path)
        return listing
    try:
        position = int(ref)
    except ValueError:
        return None
    if position < 1:
        return None
    return get_ranked_listing_at_position(position)


def _listing_for_apply(args: list[str]) -> dict | None:
    if args:
        try:
            position = int(args[0])
        except ValueError:
            return None
        if position < 1:
            return None
        return get_ranked_listing_at_position(position)
    return get_first_unapplied_ranked_listing()


def _listing_for_prep(args: list[str]) -> dict | None:
    if args:
        try:
            position = int(args[0])
        except ValueError:
            return None
        if position < 1:
            return None
        return get_ranked_listing_at_position(position)

    last_draft = get_last_draft_application()
    if last_draft:
        return _listing_with_score(last_draft["listing_id"])
    return get_ranked_listing_at_position(1)


def handle_command(chat_id: int | str, text: str) -> None:
    """Dispatch a bot command and reply to the user."""
    command, args = _command_args(text)

    if command in ("/start", "/help"):
        if command == "/start":
            notify.save_telegram_chat_id(chat_id)
            print(f"Registered chat_id {chat_id}")
            reply(chat_id, WELCOME_TEXT)
            top3 = _top_listings(limit=3)
            reply(
                chat_id,
                _format_listing_rows(
                    top3,
                    title="Top 3 right now",
                    empty_message="No scored listings yet. Try /run to refresh.",
                ),
            )
        else:
            reply(chat_id, HELP_TEXT)
        return

    if command == "/top":
        listings = _top_listings(limit=5)
        reply(
            chat_id,
            _format_listing_rows(
                listings,
                title="Top 5 matches (late Jul–Aug 18, ≤$1300)",
                empty_message="No matches. Try /run to refresh.",
            ),
        )
        return

    if command == "/august":
        listings = get_ranked_listings(limit=5, exclude_scams=True)
        reply(
            chat_id,
            _format_listing_rows(
                listings,
                title="Matches — late Jul–Aug 18, ≤$1300",
                empty_message="No matches in band. Try /run to refresh.",
            ),
        )
        return

    if command == "/tram":
        listings = _listings_by_transit_tier("muni_tram", limit=5)
        reply(
            chat_id,
            _format_listing_rows(
                listings,
                title="Top 5 — Muni Metro/tram",
                empty_message="No Muni Metro/tram listings found. Try /run first.",
            ),
        )
        return

    if command == "/caltrain":
        listings = _listings_by_transit_tier("caltrain", limit=5)
        reply(
            chat_id,
            _format_listing_rows(
                listings,
                title="Top 5 — Caltrain-adjacent",
                empty_message="No Caltrain-adjacent listings found. Try /run first.",
            ),
        )
        return

    if command == "/status":
        reply(chat_id, _status_message())
        return

    if command == "/run":
        reply(
            chat_id,
            "Starting scout → filter → rank. This takes ~3 minutes…",
        )
        try:
            init_pipeline_tables()
            results = run_pipeline(("scout", "filter", "rank"))
            reply(chat_id, _pipeline_summary(results))
        except Exception as exc:
            print(f"/run failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Pipeline error: {exc}")
        return

    if command == "/run fb" or command == "/runfb":
        reply(chat_id, "Starting scout + Facebook → filter → rank…")
        try:
            init_pipeline_tables()
            results = run_pipeline(("scout", "facebook", "filter", "rank"))
            reply(chat_id, _pipeline_summary(results))
        except Exception as exc:
            reply(chat_id, f"Pipeline error: {exc}")
        return

    if command == "/fb" or command.startswith("/fb "):
        from facebook_session import login_instructions, session_configured

        sub = command.split(maxsplit=1)[1].strip().lower() if " " in command else ""
        if sub == "poll":
            if not session_configured():
                reply(chat_id, login_instructions())
                return
            reply(chat_id, "Polling Facebook Marketplace…")
            try:
                import scout_facebook

                counts = scout_facebook.run_poll_cycle()
                listing_filter.run()
                rank_module.run()
                reply(
                    chat_id,
                    "Facebook poll done.\n"
                    f"New: {counts.get('new', 0)} · updated: {counts.get('updated', 0)}\n"
                    "Use /top for matches.",
                )
            except Exception as exc:
                reply(chat_id, f"Facebook poll failed: {exc}")
            return
        status = "logged in ✓" if session_configured() else "not logged in"
        reply(
            chat_id,
            f"Facebook Marketplace ({status})\n\n{login_instructions()}",
        )
        return

    if command == "/batch":
        try:
            init_pipeline_tables()
            try:
                import batch_apply

                count, html_path, _ = batch_apply.run(top=5)
                if count > 0 and html_path.exists():
                    reply(
                        chat_id,
                        f"Batch apply: {count} draft(s) created.\n"
                        f"Open: file://{html_path}",
                    )
                    return
            except Exception as batch_exc:
                print(f"/batch local run failed: {batch_exc}", file=sys.stderr)

            listings = get_unapplied_ranked_listings(limit=3)
            if not listings:
                reply(
                    chat_id,
                    "No unapplied listings for batch apply. Try /run first.",
                )
                return
            lines = [
                "Batch apply — run locally for the full HTML page:",
                "python batch_apply.py --top 20",
                "",
                "Top unapplied listings:",
            ]
            for i, row in enumerate(listings, 1):
                title = (row.get("title") or "Untitled")[:50]
                price = f"${row['price']}" if row.get("price") else "N/A"
                lines.append(f"{i}. [{row.get('score', 0)}] {title}")
                lines.append(f"   {price} · {row.get('url', '')}")
            reply(chat_id, "\n".join(lines))
        except Exception as exc:
            print(f"/batch failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Batch error: {exc}")
        return

    if command == "/dead":
        url = " ".join(args).strip()
        if not url:
            reply(chat_id, "Usage: /dead <craigslist url>")
            return
        try:
            init_pipeline_tables()
            listing = mark_listing_unavailable(url, reason="User reported: not available")
            if listing is None:
                reply(chat_id, "Listing not found in database.")
                return
            title = (listing.get("title") or "Listing")[:50]
            reply(
                chat_id,
                f"Marked unavailable — won't appear in rankings again.\n"
                f"{title}\n{listing.get('url', '')}",
            )
        except Exception as exc:
            print(f"/dead failed: {exc}", file=sys.stderr)
            reply(chat_id, f"Error: {exc}")
        return

    if command == "/draft":
        try:
            init_pipeline_tables()
            listing = _listing_for_apply(args)
            if listing is None:
                reply(chat_id, "No unapplied listing found for that rank.")
                return
            from gmail_draft import create_gmail_draft, format_result

            profile = load_profile()
            create_application(listing["id"], profile)
            summary = create_gmail_draft(listing, profile)
            reply(chat_id, format_result(summary, listing))
        except Exception as exc:
            print(f"/draft failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Draft error: {exc}")
        return

    if command == "/apply":
        try:
            init_pipeline_tables()
            listing = _listing_for_apply(args)
            if listing is None:
                reply(
                    chat_id,
                    "No listing found for that rank, or all top listings are already applied.",
                )
                return
            profile = load_profile()
            result = create_application(listing["id"], profile)
            reply(
                chat_id,
                format_apply_message(result)
                + "\n\nFor a Gmail draft: /draft or /draft 2",
            )
        except Exception as exc:
            print(f"/apply failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Apply error: {exc}")
        return

    if command == "/send":
        try:
            init_pipeline_tables()
            if args:
                listing = _resolve_listing_ref(" ".join(args))
            else:
                listing = get_first_unapplied_ranked_listing()
            if listing is None:
                reply(
                    chat_id,
                    "No listing found. Use /send 3 or /send <url>.",
                )
                return

            to_email = send_mail.extract_listing_email(listing)
            title = (listing.get("title") or listing["id"])[:60]
            url = listing.get("url", "")

            if not to_email:
                reply(
                    chat_id,
                    "Cannot auto-send — Craigslist has no public landlord email.\n\n"
                    f"{title}\n{url}\n\n"
                    "Craigslist replies need a browser (Reply button + relay token). "
                    "A GCP API key cannot send Gmail.\n\n"
                    "What works:\n"
                    "1. /apply — copy-paste draft into Craigslist Reply\n"
                    "2. Gmail OAuth or App Password — send when you have a direct TO address\n"
                    "3. mail_monitor — read inbox for landlord replies (/gmail status)\n\n"
                    "TODO: Playwright automation for Craigslist Reply form (not built yet).",
                )
                return

            dry_run = not mail_monitor.gmail_configured()
            if dry_run:
                reply(
                    chat_id,
                    "Gmail not configured — dry-run preview only.\n"
                    "Run /gmail auth (OAuth) or set GMAIL_APP_PASSWORD in .env.\n\n"
                    f"Found email in listing: {to_email}",
                )
            else:
                reply(
                    chat_id,
                    f"Sending email to {to_email}…\n{title}",
                )

            profile = load_profile()
            result = send_mail.send_to_listing(
                listing["id"],
                profile=profile,
                dry_run=dry_run,
            )
            reply(chat_id, send_mail.format_send_summary(result))
        except send_mail.GmailNotConfiguredError as exc:
            reply(chat_id, f"Gmail not configured:\n{exc}")
        except Exception as exc:
            print(f"/send failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Send error: {exc}")
        return

    if command in ("/sent", "/sentall", "/applied", "/replied", "/rechannel"):
        try:
            init_pipeline_tables()

            if command == "/sentall":
                channel, _ = parse_channel_args(args, default="craigslist")
                count = mark_all_drafts_sent(channel=channel)
                stats = get_application_stats()
                icon = channel_icon(channel)
                label = channel_label(channel)
                reply(
                    chat_id,
                    f"Catch-up: marked {count} draft(s) as sent {icon} ({label})\n\n"
                    f"Pipeline: sent {stats.get('sent', 0)} · replied "
                    f"{stats.get('replied', 0)} · rejected {stats.get('rejected', 0)} · "
                    f"awaiting fresh {stats.get('awaiting_fresh', 0)}",
                )
                return

            if command == "/rechannel":
                channel, remaining = parse_channel_args(args, default="craigslist")
                if not remaining:
                    reply(
                        chat_id,
                        "Usage: /rechannel imessage 3 · /rechannel email <url>",
                    )
                    return
                listing = _resolve_listing_ref(" ".join(remaining))
                if listing is None:
                    reply(chat_id, "Listing not found. Use rank number or full URL.")
                    return
                app = update_application_channel(listing["id"], channel=channel)
                if app is None:
                    reply(
                        chat_id,
                        "No application tracked for that listing yet. Use /sent first.",
                    )
                    return
                title = (listing.get("title") or listing["id"])[:60]
                icon = channel_icon(channel)
                label = channel_label(channel)
                reply(
                    chat_id,
                    f"Updated channel {icon} {label}\n{title}\n"
                    f"Status: {app['status']}",
                )
                return

            if command == "/replied":
                last_sent = get_last_sent_application()
                if last_sent is None:
                    reply(chat_id, "No sent application to mark as replied.")
                    return
                updated = update_application_status(last_sent["id"], "replied")
                listing = _listing_with_score(last_sent["listing_id"])
                title = (listing or {}).get("title", last_sent["listing_id"])
                reply(
                    chat_id,
                    f"Marked as replied 💬\n{(title or '')[:60]}\n"
                    f"Status: {updated['status'] if updated else 'replied'}",
                )
                return

            if command == "/sent":
                channel, remaining = parse_channel_args(args, default="craigslist")
                if not remaining:
                    reply(
                        chat_id,
                        "Usage: /sent 3 · /sent imessage <url> · /sentall email",
                    )
                    return
                listing = _resolve_listing_ref(" ".join(remaining))
                if listing is None:
                    reply(chat_id, "Listing not found. Use rank number or full URL.")
                    return
                app = mark_application_sent(listing["id"], channel=channel)
                title = (listing.get("title") or listing["id"])[:60]
                icon = channel_icon(channel)
                label = channel_label(channel)
                reply(
                    chat_id,
                    f"Marked as sent {icon} ({label})\n{title}\n"
                    f"Status: {app['status'] if app else 'sent'}",
                )
                return

            # /applied — legacy alias for last draft
            channel, _ = parse_channel_args(args, default="craigslist")
            last_draft = get_last_draft_application()
            if last_draft is None:
                reply(chat_id, "No draft to mark as sent. Use /apply first.")
                return
            app = mark_application_sent(last_draft["listing_id"], channel=channel)
            listing = _listing_with_score(last_draft["listing_id"])
            title = (listing or {}).get("title", last_draft["listing_id"])
            icon = channel_icon(channel)
            label = channel_label(channel)
            reply(
                chat_id,
                f"Marked as sent {icon} ({label})\n{(title or '')[:60]}\n"
                f"Status: {app['status'] if app else 'sent'}",
            )
        except Exception as exc:
            print(f"{command} failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Tracking error: {exc}")
        return

    if command == "/apps":
        try:
            init_pipeline_tables()
            reply(chat_id, _format_apps_message())
        except Exception as exc:
            print(f"/apps failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Apps error: {exc}")
        return

    if command == "/gmail":
        try:
            sub = (args[0].lower() if args else "status")
            if sub == "auth":
                reply(chat_id, _format_gmail_auth_instructions())
                return
            if sub in ("status", "help"):
                reply(chat_id, _format_gmail_status_message())
                return
            reply(
                chat_id,
                "Usage: /gmail status · /gmail auth",
            )
        except Exception as exc:
            print(f"/gmail failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Gmail status error: {exc}")
        return

    if command == "/comm":
        try:
            import communication_page

            init_pipeline_tables()
            path = communication_page.run(
                check_mail=mail_monitor.gmail_configured(),
                open_browser=False,
            )
            stats = get_application_stats()
            reply(
                chat_id,
                "Follow-up page updated.\n"
                f"Draft {stats.get('draft', 0)} · sent {stats.get('sent', 0)} · "
                f"replied {stats.get('replied', 0)}\n\n"
                f"Open on Mac:\nfile://{path}\n\n"
                "Or: python communication_page.py --open",
            )
        except Exception as exc:
            reply(chat_id, f"Comm page error: {exc}")
        return

    if command == "/mail":
        try:
            init_pipeline_tables()
            if args and args[0].lower() == "loop":
                reply(
                    chat_id,
                    "Background mailbox polling:\n\n"
                    "python mail_monitor.py --loop 300\n\n"
                    "Runs every 5 minutes. Keep the terminal open, or use cron:\n"
                    "*/5 * * * * cd /path/to/2607-lookingforroom && "
                    ".venv/bin/python mail_monitor.py",
                )
                return
            dry_run = not mail_monitor.gmail_configured()
            result = mail_monitor.check_inbox(dry_run=dry_run)
            reply(chat_id, mail_monitor.format_check_summary(result))
        except Exception as exc:
            print(f"/mail failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Mail check error: {exc}")
        return

    if command == "/prep":
        try:
            init_pipeline_tables()
            listing = _listing_for_prep(args)
            if listing is None:
                reply(chat_id, "No listing found for tour prep.")
                return
            profile = load_profile()
            reply(chat_id, format_prep_message(listing, profile))
        except Exception as exc:
            print(f"/prep failed: {exc}", file=sys.stderr)
            traceback.print_exc()
            reply(chat_id, f"Prep error: {exc}")
        return

    reply(chat_id, "Unknown command. Try /help")


def process_update(update: dict[str, Any]) -> None:
    """Handle one Telegram update."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or ""
    if chat_id is None or not text.startswith("/"):
        return

    try:
        handle_command(chat_id, text)
    except Exception as exc:
        print(f"command handler error: {exc}", file=sys.stderr)
        traceback.print_exc()
        reply(chat_id, f"Something went wrong: {exc}")


def poll_once(offset: int | None) -> tuple[int | None, list[dict[str, Any]]]:
    """Fetch updates via long polling. Returns (next_offset, updates)."""
    params: dict[str, Any] = {"timeout": POLL_TIMEOUT_SEC}
    if offset is not None:
        params["offset"] = offset

    response = requests.get(
        f"{_api_base()}/getUpdates",
        params=params,
        timeout=POLL_TIMEOUT_SEC + 10,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"getUpdates failed: {payload}")

    updates = payload.get("result") or []
    next_offset = offset
    for update in updates:
        update_id = int(update["update_id"])
        next_offset = update_id + 1
    return next_offset, updates


def run_bot() -> None:
    """Long-polling loop until interrupted."""
    print("SF Room Finder bot — long polling (Ctrl+C to stop)")
    print(f"Users: open {BOT_LINK} and tap Start")

    offset: int | None = None
    while True:
        try:
            offset, updates = poll_once(offset)
            for update in updates:
                process_update(update)
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                print("poll conflict (another bot instance?) — retrying in 10s", file=sys.stderr)
                time.sleep(10)
            else:
                print(f"poll error: {exc}", file=sys.stderr)
                time.sleep(5)
        except requests.RequestException as exc:
            print(f"poll error: {exc}", file=sys.stderr)
            time.sleep(5)
        except Exception as exc:
            print(f"unexpected error: {exc}", file=sys.stderr)
            traceback.print_exc()
            time.sleep(5)


def main() -> int:
    if not TELEGRAM_BOT_TOKEN:
        print("Set TELEGRAM_BOT_TOKEN in .env before running bot.py", file=sys.stderr)
        return 1
    run_bot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())