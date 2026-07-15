#!/usr/bin/env python3
"""Send room inquiry emails via Gmail SMTP (App Password).

Uses the same credentials as mail_monitor.py:
  GMAIL_ADDRESS + GMAIL_APP_PASSWORD

A Google Cloud API key cannot send Gmail — only App Password SMTP (or OAuth2).

Usage:
    python send_mail.py --dry-run --to landlord@example.com
    python send_mail.py --to landlord@example.com
    python send_mail.py --listing-url https://sfbay.craigslist.org/...
    python send_mail.py --top 3
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import smtplib
import sys
from email.message import EmailMessage
from typing import Any

from dotenv import load_dotenv

from lfr.apply import build_draft, load_profile, resolve_listing
from lfr.db import (
    _listing_with_score,
    get_listing_by_id,
    init_db,
    mark_application_sent,
    upsert_application_draft,
)
from lfr.mail.gmail_creds import SETUP_INSTRUCTIONS, auth_mode as gmail_auth_mode, gmail_configured
from lfr.mail.gmail_creds import gmail_address as _from_profile_address
from lfr.mail.gmail_creds import gmail_password as _gmail_password

load_dotenv()

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
DEFAULT_EMAIL_SUBJECT = "Room Rental Inquiry by Aug 18"

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

EMAIL_BLOCKLIST_DOMAINS = (
    "craigslist.org",
    "reply.craigslist.org",
    "example.com",
    "test.com",
    "sentry.io",
)

CRAIGSLIST_NO_EMAIL_MSG = (
    "This Craigslist listing has no public landlord email in the description. "
    "Craigslist hides contact addresses — replies go through their relay form "
    "(browser + SERVICE_ID token). Open the listing URL and click Reply manually, "
    "or paste your draft from /apply."
)


class GmailNotConfiguredError(RuntimeError):
    """Raised when GMAIL_ADDRESS or GMAIL_APP_PASSWORD is missing."""


class CraigslistNoEmailError(RuntimeError):
    """Raised when a listing description has no extractable direct email."""


def _from_address(profile: dict[str, Any]) -> str:
    addr = _from_profile_address()
    if addr:
        return addr
    return str(profile.get("email", "")).strip()


def _app_password() -> str:
    return _gmail_password()


def _email_subject(profile: dict[str, Any]) -> str:
    subject = str(profile.get("email_subject") or "").strip()
    return subject or DEFAULT_EMAIL_SUBJECT


def _is_blocked_email(email: str) -> bool:
    lowered = email.lower()
    domain = lowered.rsplit("@", 1)[-1]
    if domain in EMAIL_BLOCKLIST_DOMAINS:
        return True
    if "craigslist" in domain:
        return True
    if lowered.startswith("noreply@") or lowered.startswith("no-reply@"):
        return True
    return False


def extract_email_from_text(text: str) -> str | None:
    """Return the first plausible direct contact email in free text."""
    if not text:
        return None
    for match in EMAIL_PATTERN.findall(text):
        candidate = match.strip().rstrip(".,;)")
        if _is_blocked_email(candidate):
            continue
        return candidate
    return None


def extract_listing_email(listing: dict[str, Any]) -> str | None:
    """Try to find a landlord email in listing title + description."""
    combined = " ".join(
        str(listing.get(field) or "")
        for field in ("title", "description")
    )
    return extract_email_from_text(combined)


def build_email_body(
    profile: dict[str, Any],
    listing: dict[str, Any] | None = None,
) -> str:
    """Inquiry body from profile template; personalized when listing is given."""
    if listing is not None:
        return build_draft(listing, profile)
    template = (profile.get("message_template") or "").strip()
    if not template:
        raise ValueError("profile.yaml message_template is empty")
    return template


def _build_email_message(
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def _gmail_api_send(
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    import lfr.mail.gmail_auth

    msg = _build_email_message(
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body=body,
    )
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    service = gmail_auth.get_gmail_service()
    service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()


def _smtp_send(
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    password = _app_password()
    if not password:
        raise GmailNotConfiguredError(SETUP_INSTRUCTIONS)

    msg = _build_email_message(
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body=body,
    )

    with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=60) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(from_addr, password)
        smtp.send_message(msg)


def _deliver_email(
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    dry_run: bool,
) -> str:
    """Send via Gmail API (OAuth) or SMTP (App Password). Returns channel label."""
    if dry_run:
        return "dry-run"

    mode = gmail_auth_mode()
    if mode == "oauth":
        _gmail_api_send(
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
        )
        return "gmail_api"
    if mode == "app_password":
        _smtp_send(
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
            dry_run=False,
        )
        return "smtp"
    raise GmailNotConfiguredError(SETUP_INSTRUCTIONS)


def send_inquiry(
    to_email: str,
    listing: dict[str, Any] | None = None,
    *,
    profile: dict[str, Any] | None = None,
    dry_run: bool = False,
    mark_sent: bool = True,
) -> dict[str, Any]:
    """Send one inquiry email. Optionally ties to a listing and marks sent."""
    to_addr = (to_email or "").strip()
    if not to_addr or "@" not in to_addr:
        raise ValueError(f"Invalid recipient: {to_email!r}")

    profile_data = profile or load_profile()
    from_addr = _from_address(profile_data)
    if not from_addr:
        raise GmailNotConfiguredError(
            "Set GMAIL_ADDRESS in .env or email in profile.yaml"
        )

    if not dry_run and not gmail_configured():
        raise GmailNotConfiguredError(SETUP_INSTRUCTIONS)

    subject = _email_subject(profile_data)
    body = build_email_body(profile_data, listing)

    channel = _deliver_email(
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body=body,
        dry_run=dry_run,
    )

    result: dict[str, Any] = {
        "from": from_addr,
        "to": to_addr,
        "subject": subject,
        "body": body,
        "dry_run": dry_run,
        "channel": channel,
        "listing_id": listing.get("id") if listing else None,
        "application": None,
    }

    if listing is not None and mark_sent and not dry_run:
        upsert_application_draft(listing["id"], body, status="draft")
        result["application"] = mark_application_sent(
            listing["id"],
            channel="email",
            notes=f"{channel} to {to_addr}",
        )

    return result


def send_to_listing(
    listing_id: str,
    *,
    profile: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send inquiry only if listing text contains a direct email address."""
    init_db()
    listing = _listing_with_score(listing_id)
    if listing is None:
        row = get_listing_by_id(listing_id)
        if row is not None:
            listing = _listing_with_score(row["id"])
    if listing is None:
        raise ValueError(f"Listing not found: {listing_id}")

    to_email = extract_listing_email(listing)
    if not to_email:
        raise CraigslistNoEmailError(CRAIGSLIST_NO_EMAIL_MSG)

    return send_inquiry(
        to_email,
        listing=listing,
        profile=profile,
        dry_run=dry_run,
    )


def format_send_summary(result: dict[str, Any]) -> str:
    """Human-readable summary for CLI or Telegram."""
    title_bit = ""
    if result.get("listing_id"):
        title_bit = f"\nListing: {result['listing_id']}"
    if result.get("dry_run"):
        mode = "DRY RUN — would send"
    else:
        send_channel = result.get("channel") or "sent"
        mode = f"Sent ({send_channel})"
    app = result.get("application")
    tracked = ""
    if app:
        tracked = f"\nTracked: status={app.get('status')} channel={app.get('channel')}"
    elif result.get("dry_run") and result.get("listing_id"):
        tracked = "\nTracked: skipped (dry-run)"

    body_preview = (result.get("body") or "")[:200]
    if len(result.get("body") or "") > 200:
        body_preview += "…"

    return (
        f"{mode} email inquiry\n"
        f"From: {result.get('from')}\n"
        f"To: {result.get('to')}\n"
        f"Subject: {result.get('subject')}"
        f"{title_bit}"
        f"{tracked}\n"
        f"{'-' * 40}\n"
        f"{body_preview}"
    )


def _resolve_cli_listing(
    *,
    listing_url: str | None,
    listing_id: str | None,
    top: int | None,
) -> dict[str, Any] | None:
    if top is not None:
        from lfr.db import get_ranked_listing_at_position

        return get_ranked_listing_at_position(top)
    if listing_url:
        return resolve_listing(listing_url)
    if listing_id:
        return _listing_with_score(listing_id) or get_listing_by_id(listing_id)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Send room inquiry via Gmail SMTP (App Password)",
    )
    parser.add_argument(
        "--to",
        metavar="EMAIL",
        help="Recipient email (direct send; use with optional --listing-url for context)",
    )
    parser.add_argument(
        "--listing-url",
        metavar="URL",
        help="Craigslist listing URL — send only if description has a direct email",
    )
    parser.add_argument(
        "--listing-id",
        metavar="ID",
        help="Listing id (e.g. 7856123456.html)",
    )
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Nth ranked listing (1 = best) — send only if direct email found",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview message without SMTP or DB updates",
    )
    ns = parser.parse_args(argv)

    targets = sum(
        1
        for flag in (ns.to, ns.listing_url, ns.listing_id, ns.top is not None)
        if flag
    )
    if targets == 0:
        parser.print_help()
        return 1
    if targets > 1 and not (ns.to and (ns.listing_url or ns.listing_id)):
        print(
            "Use one of --to, --listing-url, --listing-id, or --top "
            "(or --to with --listing-url for personalized body + tracking).",
            file=sys.stderr,
        )
        return 1

    try:
        init_db()
        profile = load_profile()

        if ns.to and not ns.listing_url and not ns.listing_id and ns.top is None:
            result = send_inquiry(ns.to, dry_run=ns.dry_run, mark_sent=False)
            print(format_send_summary(result))
            return 0

        listing = _resolve_cli_listing(
            listing_url=ns.listing_url,
            listing_id=ns.listing_id,
            top=ns.top,
        )
        if listing is None:
            print("Listing not found.", file=sys.stderr)
            return 1

        if ns.to:
            result = send_inquiry(
                ns.to,
                listing=listing,
                profile=profile,
                dry_run=ns.dry_run,
            )
        else:
            result = send_to_listing(
                listing["id"],
                profile=profile,
                dry_run=ns.dry_run,
            )

        print(format_send_summary(result))
        return 0
    except CraigslistNoEmailError as exc:
        print(f"Cannot send: {exc}", file=sys.stderr)
        return 2
    except (GmailNotConfiguredError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except smtplib.SMTPException as exc:
        print(f"SMTP error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())