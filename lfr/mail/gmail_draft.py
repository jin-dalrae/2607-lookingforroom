#!/usr/bin/env python3
"""Create Gmail drafts via IMAP — open Gmail and click Send."""

from __future__ import annotations

import argparse
import email.utils
import imaplib
import sys
import time
from email.mime.text import MIMEText
from typing import Any

from lfr.apply import create_application, load_profile, resolve_listing, standard_apply_message
from lfr.db import (
    get_first_unapplied_ranked_listing,
    get_ranked_listing_at_position,
    get_unapplied_ranked_listings,
    init_db,
)
from lfr.mail.gmail_creds import SETUP_INSTRUCTIONS, gmail_address, gmail_configured, gmail_password
from lfr.mail.send_mail import extract_listing_email

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
DRAFTS_FOLDER = "[Gmail]/Drafts"


def _connect_imap() -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
    client.login(gmail_address(), gmail_password())
    return client


def _subject_for_listing(_listing: dict[str, Any], profile: dict[str, Any]) -> str:
    return (profile.get("email_subject") or "Room Rental Inquiry by Aug 18").strip()


def _body_for_listing(listing: dict[str, Any], profile: dict[str, Any]) -> str:
    return standard_apply_message(profile, listing.get("url") or "")


def _draft_message(
    listing: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[MIMEText, dict[str, Any]]:
    from_addr = gmail_address()
    to_addr = extract_listing_email(listing) or ""
    subject = _subject_for_listing(listing, profile)
    body = _body_for_listing(listing, profile)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    if to_addr:
        msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)

    summary = {
        "subject": subject,
        "to": to_addr or "(add Craigslist reply address)",
        "from": from_addr,
        "listing_url": listing.get("url"),
    }
    return msg, summary


def create_gmail_draft(
    listing: dict[str, Any],
    profile: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    client: imaplib.IMAP4_SSL | None = None,
) -> dict[str, Any]:
    """Append a message to Gmail Drafts. Returns summary dict."""
    profile_data = profile or load_profile()
    msg, summary = _draft_message(listing, profile_data)
    summary["dry_run"] = dry_run

    if dry_run:
        summary["body_preview"] = msg.get_payload()
        return summary

    own_client = client is None
    imap_client = client or _connect_imap()
    try:
        internal_date = imaplib.Time2Internaldate(time.time())
        imap_client.append(
            DRAFTS_FOLDER,
            "\\Draft",
            internal_date,
            msg.as_bytes(),
        )
    finally:
        if own_client:
            try:
                imap_client.logout()
            except Exception:
                pass

    summary["saved"] = True
    return summary


def create_gmail_drafts_batch(
    listings: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Create Gmail drafts for multiple listings; one IMAP session."""
    profile_data = profile or load_profile()
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if not listings:
        return results

    if dry_run:
        for listing in listings:
            summary = create_gmail_draft(listing, profile_data, dry_run=True)
            results.append((listing, summary))
        return results

    client = _connect_imap()
    try:
        for listing in listings:
            create_application(listing["id"], profile_data)
            summary = create_gmail_draft(
                listing, profile_data, client=client
            )
            results.append((listing, summary))
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return results


def format_result(summary: dict[str, Any], listing: dict[str, Any]) -> str:
    title = (listing.get("title") or "Untitled")[:60]
    price = f"${listing['price']}" if listing.get("price") else "N/A"
    lines = [
        "Gmail draft created ✉️",
        f"{title}",
        f"{price} · {listing.get('neighborhood', '')}",
        f"To: {summary.get('to')}",
        f"Subject: {summary.get('subject')}",
        "",
        "Open Gmail → Drafts → review → Send",
        f"{listing.get('url', '')}",
    ]
    if not extract_listing_email(listing):
        lines.insert(
            6,
            "Craigslist: open the listing → click Reply → copy the "
            "reply@…craigslist.org address → paste into Gmail’s To field.",
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Gmail draft for a room listing")
    parser.add_argument("listing_ref", nargs="?", help="Listing URL or id")
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Draft first N unapplied matches (default 1 if no other mode)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Draft all unapplied matches (up to pool limit)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.dry_run and not gmail_configured():
        print(SETUP_INSTRUCTIONS, file=sys.stderr)
        return 1

    init_db()
    profile = load_profile()

    try:
        if args.all:
            listings = get_unapplied_ranked_listings(limit=50, pool_limit=50)
            if not listings:
                print("No unapplied matches found.", file=sys.stderr)
                return 1
            batch = create_gmail_drafts_batch(
                listings, profile, dry_run=args.dry_run
            )
            print(f"Gmail drafts: {len(batch)} created")
            for i, (listing, summary) in enumerate(batch, 1):
                title = (listing.get("title") or "Untitled")[:55]
                price = f"${listing['price']}" if listing.get("price") else "N/A"
                print(f"\n{i}. {title}")
                print(f"   {price} · {listing.get('neighborhood', '')}")
                print(f"   To: {summary.get('to')}")
                print(f"   {listing.get('url', '')}")
            print("\nOpen Gmail → Drafts → paste Craigslist reply email into To → Send each")
            return 0

        if args.top is not None and args.top > 1:
            listings = get_unapplied_ranked_listings(limit=args.top, pool_limit=150)
            if not listings:
                print("No unapplied matches found.", file=sys.stderr)
                return 1
            batch = create_gmail_drafts_batch(
                listings, profile, dry_run=args.dry_run
            )
            print(f"Gmail drafts: {len(batch)} created")
            for i, (listing, summary) in enumerate(batch, 1):
                print(format_result(summary, listing))
                print()
            return 0

        if args.top is not None:
            rows = get_unapplied_ranked_listings(limit=args.top, pool_limit=150)
            listing = rows[args.top - 1] if len(rows) >= args.top else None
        elif args.listing_ref:
            listing = resolve_listing(args.listing_ref)
        else:
            listing = get_first_unapplied_ranked_listing()

        if listing is None:
            print("No listing found.", file=sys.stderr)
            return 1

        if not args.dry_run:
            create_application(listing["id"], profile)
        summary = create_gmail_draft(listing, profile, dry_run=args.dry_run)
        print(format_result(summary, listing))
        if args.dry_run:
            print("\n--- body preview ---\n")
            print(summary.get("body_preview", ""))
        return 0
    except imaplib.IMAP4.error as exc:
        print(f"IMAP error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())