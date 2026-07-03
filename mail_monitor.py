#!/usr/bin/env python3
"""Monitor Gmail inbox for landlord replies to Craigslist room inquiries.

Requires a Google App Password (not your regular Gmail password):
  https://myaccount.google.com/apppasswords

Usage:
    python mail_monitor.py              # one inbox check
    python mail_monitor.py --loop 300   # poll every 5 minutes
    python mail_monitor.py --dry-run    # preview matches without DB updates
"""

from __future__ import annotations

import argparse
import base64
import email
import imaplib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

import notify
from db import (
    get_listing_by_id,
    get_sent_applications,
    init_pipeline_tables,
    is_mail_message_processed,
    mark_application_replied,
    record_mail_message,
)

load_dotenv()

import os

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
LOOKBACK_DAYS = 14
SNIPPET_LEN = 500
FUZZY_MATCH_THRESHOLD = 0.55

CRAIGSLIST_FROM_MARKERS = (
    "craigslist.org",
    "reply.craigslist",
    "hous.craigslist",
)

RENTAL_KEYWORDS = (
    "room",
    "rental",
    "listing",
    "apartment",
    "available",
    "viewing",
)

CRAIGSLIST_ID_PATTERNS = (
    re.compile(r"craigslist\.org/[^\s\"'>]+/(\d{8,})(?:\.html)?", re.I),
    re.compile(r"/view/d/[^/\s\"'>]+/(\d{8,})", re.I),
    re.compile(r"post[=:](\d{8,})", re.I),
    re.compile(r"/(\d{8,})\.html", re.I),
)




@dataclass
class ParsedEmail:
    message_id: str
    from_addr: str
    subject: str
    date: str
    snippet: str
    body_text: str


@dataclass
class MatchResult:
    listing_id: str
    title: str
    url: str
    method: str
    score: float | None = None


@dataclass
class CheckResult:
    checked: int = 0
    candidates: int = 0
    matched: list[dict[str, Any]] = field(default_factory=list)
    skipped_seen: int = 0
    unmatched: int = 0
    dry_run: bool = False
    error: str | None = None


from gmail_creds import (
    SETUP_INSTRUCTIONS as GMAIL_SETUP,
    auth_mode as gmail_auth_mode,
    gmail_address as _default_gmail_address,
    gmail_configured,
    gmail_password,
)

# Re-export for send_mail.py and bot.py
SETUP_INSTRUCTIONS = GMAIL_SETUP


def _oauth_configured() -> bool:
    try:
        import gmail_auth

        return gmail_auth.token_valid()
    except ImportError:
        return False


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(fragment))
    return "".join(parts).strip()


def _extract_body(msg: email.message.Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition.lower():
                continue
            if content_type not in ("text/plain", "text/html"):
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                chunks.append(payload.decode(charset, errors="replace"))
            except LookupError:
                chunks.append(payload.decode("utf-8", errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                chunks.append(payload.decode(charset, errors="replace"))
            except LookupError:
                chunks.append(payload.decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def _normalize_post_id(raw: str) -> str:
    raw = raw.strip().lower()
    if raw.endswith(".html"):
        return raw
    if raw.isdigit():
        return f"{raw}.html"
    return raw


def extract_craigslist_post_ids(text: str) -> list[str]:
    """Return normalized Craigslist post IDs found in email text."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in CRAIGSLIST_ID_PATTERNS:
        for match in pattern.findall(text):
            post_id = _normalize_post_id(match)
            if post_id not in seen:
                seen.add(post_id)
                found.append(post_id)
    return found


def _fuzzy_ratio(a: str, b: str) -> float:
    left = re.sub(r"\s+", " ", (a or "").lower()).strip()
    right = re.sub(r"\s+", " ", (b or "").lower()).strip()
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _post_id_variants(post_id: str) -> set[str]:
    base = post_id.removesuffix(".html")
    return {post_id, base, f"{base}.html"}


def match_email_to_application(
    parsed: ParsedEmail,
    sent_apps: list[dict[str, Any]],
) -> MatchResult | None:
    """Match an email to a sent application via post ID or fuzzy title."""
    haystack = f"{parsed.subject}\n{parsed.body_text}"

    post_ids = extract_craigslist_post_ids(haystack)
    by_id = {app["listing_id"]: app for app in sent_apps}
    for post_id in post_ids:
        for variant in _post_id_variants(post_id):
            app = by_id.get(variant)
            if app:
                return MatchResult(
                    listing_id=app["listing_id"],
                    title=app.get("title") or app["listing_id"],
                    url=app.get("url") or "",
                    method="post_id",
                )
            listing = get_listing_by_id(variant)
            if listing:
                app = by_id.get(listing["id"])
                if app:
                    return MatchResult(
                        listing_id=app["listing_id"],
                        title=app.get("title") or listing.get("title") or app["listing_id"],
                        url=app.get("url") or listing.get("url") or "",
                        method="post_id",
                    )

    best: MatchResult | None = None
    for app in sent_apps:
        title = app.get("title") or ""
        score = _fuzzy_ratio(parsed.subject, title)
        if score >= FUZZY_MATCH_THRESHOLD and (
            best is None or score > (best.score or 0)
        ):
            best = MatchResult(
                listing_id=app["listing_id"],
                title=title or app["listing_id"],
                url=app.get("url") or "",
                method="fuzzy_title",
                score=score,
            )
    return best


def _email_matches_filters(parsed: ParsedEmail) -> bool:
    from_lower = parsed.from_addr.lower()
    if any(marker in from_lower for marker in CRAIGSLIST_FROM_MARKERS):
        return True

    combined = f"{parsed.subject} {parsed.snippet}".lower()
    return any(keyword in combined for keyword in RENTAL_KEYWORDS)


def _imap_since_date(days: int = LOOKBACK_DAYS) -> str:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return since.strftime("%d-%b-%Y")


def _gmail_api_since_query(days: int = LOOKBACK_DAYS) -> str:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return f"after:{since.strftime('%Y/%m/%d')}"


def _gmail_api_header(headers: list[dict[str, str]], name: str) -> str:
    target = name.lower()
    for header in headers:
        if header.get("name", "").lower() == target:
            return header.get("value", "")
    return ""


def _extract_gmail_api_body(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")
    if payload.get("parts"):
        chunks: list[str] = []
        for part in payload["parts"]:
            chunk = _extract_gmail_api_body(part)
            if chunk:
                chunks.append(chunk)
        return "\n".join(chunks)

    body_data = payload.get("body", {}).get("data")
    if not body_data:
        return ""
    if "text/plain" not in mime_type and "text/html" not in mime_type:
        return ""

    raw = base64.urlsafe_b64decode(body_data + "==")
    return raw.decode("utf-8", errors="replace")


def _parse_gmail_api_message(msg: dict[str, Any]) -> ParsedEmail:
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []

    message_id = _gmail_api_header(headers, "Message-ID")
    if not message_id:
        message_id = f"gmail-api-{msg.get('id', 'unknown')}"

    from_addr = _gmail_api_header(headers, "From")
    subject = _gmail_api_header(headers, "Subject")
    date_hdr = _gmail_api_header(headers, "Date")
    try:
        dt = parsedate_to_datetime(date_hdr) if date_hdr else None
        date_str = dt.isoformat() if dt else date_hdr
    except (TypeError, ValueError, OverflowError):
        date_str = date_hdr

    body_text = _extract_gmail_api_body(payload)
    snippet_source = body_text or msg.get("snippet", "")
    snippet = re.sub(r"\s+", " ", snippet_source).strip()[:SNIPPET_LEN]

    return ParsedEmail(
        message_id=message_id,
        from_addr=from_addr,
        subject=subject,
        date=date_str,
        snippet=snippet,
        body_text=body_text,
    )


def _fetch_candidate_emails_api(service: Any) -> list[ParsedEmail]:
    query = _gmail_api_since_query()
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=500)
        .execute()
    )
    message_refs = response.get("messages") or []
    parsed_emails: list[ParsedEmail] = []

    for msg_ref in reversed(message_refs):
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_ref["id"], format="full")
            .execute()
        )
        candidate = _parse_gmail_api_message(msg)
        if _email_matches_filters(candidate):
            parsed_emails.append(candidate)

    return parsed_emails


def _connect_imap() -> imaplib.IMAP4_SSL:
    address = _default_gmail_address()
    password = gmail_password()
    if not address or not password:
        raise RuntimeError("Gmail credentials missing")
    client = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
    client.login(address, password)
    return client


def _fetch_candidate_emails(client: imaplib.IMAP4_SSL) -> list[ParsedEmail]:
    client.select("INBOX")
    since = _imap_since_date()
    status, data = client.search(None, f'(SINCE "{since}")')
    if status != "OK":
        raise RuntimeError(f"IMAP search failed: {status}")

    ids = (data[0] or b"").split()
    parsed_emails: list[ParsedEmail] = []

    for msg_id in reversed(ids):
        status, msg_data = client.fetch(msg_id, "(RFC822)")
        if status != "OK" or not msg_data:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        message_id = _decode_mime_header(msg.get("Message-ID"))
        if not message_id:
            message_id = f"imap-{msg_id.decode('ascii', errors='replace')}"

        from_addr = _decode_mime_header(msg.get("From"))
        subject = _decode_mime_header(msg.get("Subject"))
        date_hdr = _decode_mime_header(msg.get("Date"))
        try:
            dt = parsedate_to_datetime(date_hdr) if date_hdr else None
            date_str = dt.isoformat() if dt else date_hdr
        except (TypeError, ValueError, OverflowError):
            date_str = date_hdr

        body_text = _extract_body(msg)
        snippet = re.sub(r"\s+", " ", body_text).strip()[:SNIPPET_LEN]

        candidate = ParsedEmail(
            message_id=message_id,
            from_addr=from_addr,
            subject=subject,
            date=date_str,
            snippet=snippet,
            body_text=body_text,
        )
        if _email_matches_filters(candidate):
            parsed_emails.append(candidate)

    return parsed_emails


def _email_meta(parsed: ParsedEmail) -> dict[str, Any]:
    return {
        "message_id": parsed.message_id,
        "from": parsed.from_addr,
        "subject": parsed.subject,
        "date": parsed.date,
        "snippet": parsed.snippet,
    }


def _format_telegram_alert(parsed: ParsedEmail, match: MatchResult) -> str:
    lines = [
        "💬 Landlord reply matched",
        f"Listing: {(match.title or 'Untitled')[:70]}",
        f"Subject: {parsed.subject[:120]}",
        f"From: {parsed.from_addr[:80]}",
        "",
        parsed.snippet[:400],
    ]
    if match.url:
        lines.extend(["", match.url])
    return "\n".join(lines)


def check_inbox(*, dry_run: bool | None = None) -> CheckResult:
    """Run one inbox scan. Returns summary of matches and skips."""
    init_pipeline_tables()
    result = CheckResult(dry_run=bool(dry_run))

    if dry_run is None:
        result.dry_run = not gmail_configured()

    if not gmail_configured():
        print(SETUP_INSTRUCTIONS)
        if result.dry_run:
            sent_apps = get_sent_applications()
            print(
                f"\n[dry-run] Would check inbox for {len(sent_apps)} sent application(s)."
            )
            result.error = "credentials_missing"
        return result

    sent_apps = get_sent_applications()
    if not sent_apps:
        print("No sent applications to match against. Mark listings /sent first.")
        return result

    use_imap = gmail_configured()
    use_oauth = not use_imap and _oauth_configured()
    client: imaplib.IMAP4_SSL | None = None
    gmail_service: Any | None = None

    try:
        if use_imap:
            client = _connect_imap()
            candidates = _fetch_candidate_emails(client)
        elif use_oauth:
            import gmail_auth

            gmail_service = gmail_auth.get_gmail_service()
            candidates = _fetch_candidate_emails_api(gmail_service)
        else:
            raise RuntimeError("No Gmail credentials")
    except imaplib.IMAP4.error as exc:
        result.error = str(exc)
        print(f"IMAP login failed: {exc}", file=sys.stderr)
        print(SETUP_INSTRUCTIONS)
        return result
    except Exception as exc:
        result.error = str(exc)
        label = "Gmail API" if use_oauth else "IMAP"
        print(f"{label} error: {exc}", file=sys.stderr)
        if not use_oauth:
            print(SETUP_INSTRUCTIONS)
        return result

    try:
        result.checked = len(candidates)

        for parsed in candidates:
            if is_mail_message_processed(parsed.message_id):
                result.skipped_seen += 1
                continue

            result.candidates += 1
            match = match_email_to_application(parsed, sent_apps)
            if match is None:
                result.unmatched += 1
                if not result.dry_run:
                    record_mail_message(
                        message_id=parsed.message_id,
                        from_addr=parsed.from_addr,
                        subject=parsed.subject,
                        email_date=parsed.date,
                        snippet=parsed.snippet,
                        matched_listing_id=None,
                        match_method=None,
                    )
                continue

            email_meta = _email_meta(parsed)
            entry = {
                "listing_id": match.listing_id,
                "title": match.title,
                "url": match.url,
                "method": match.method,
                "subject": parsed.subject,
                "from": parsed.from_addr,
            }
            result.matched.append(entry)

            if result.dry_run:
                print(
                    f"[dry-run] Would mark replied: {match.title[:60]} "
                    f"({match.method})"
                )
                print(f"  Subject: {parsed.subject[:80]}")
                continue

            updated = mark_application_replied(
                match.listing_id,
                email_meta=email_meta,
            )
            record_mail_message(
                message_id=parsed.message_id,
                from_addr=parsed.from_addr,
                subject=parsed.subject,
                email_date=parsed.date,
                snippet=parsed.snippet,
                matched_listing_id=match.listing_id,
                match_method=match.method,
            )
            notify.send_telegram(_format_telegram_alert(parsed, match))
            status = updated["status"] if updated else "replied"
            print(f"Marked replied ({status}): {match.title[:60]} [{match.method}]")
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass

    return result


def format_check_summary(result: CheckResult) -> str:
    if result.error == "credentials_missing":
        return (
            "Mailbox not configured.\n"
            "Use OAuth (python oauth_setup.py) or set GMAIL_ADDRESS + "
            "GMAIL_APP_PASSWORD in .env (see README → Mailbox monitoring)."
        )

    mode = gmail_auth_mode()
    mode_label = {
        "oauth": "Gmail API (OAuth)",
        "app_password": "IMAP (App Password)",
        "none": "not configured",
    }.get(mode, mode)

    lines = [
        "Mailbox check complete",
        f"Auth: {mode_label}",
        f"Candidates (14d): {result.checked}",
        f"New to process: {result.candidates}",
        f"Already seen: {result.skipped_seen}",
        f"Matched replies: {len(result.matched)}",
        f"Unmatched: {result.unmatched}",
    ]
    if result.dry_run:
        lines.append("Mode: dry-run (no DB updates)")

    if result.matched:
        lines.append("")
        lines.append("Matches:")
        for i, row in enumerate(result.matched, 1):
            lines.append(
                f"{i}. {row['title'][:50]} ({row['method']})\n"
                f"   {row.get('subject', '')[:60]}"
            )
            if row.get("url"):
                lines.append(f"   {row['url']}")
    elif result.error:
        lines.append(f"Error: {result.error}")

    return "\n".join(lines)


def run_loop(interval_sec: int, *, dry_run: bool = False) -> None:
    print(f"Mailbox monitor — polling every {interval_sec}s (Ctrl+C to stop)")
    while True:
        try:
            result = check_inbox(dry_run=dry_run)
            print(format_check_summary(result))
            print()
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as exc:
            print(f"check failed: {exc}", file=sys.stderr)
        time.sleep(interval_sec)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gmail inbox monitor for landlord replies")
    parser.add_argument(
        "--loop",
        type=int,
        metavar="SEC",
        help="Poll inbox every SEC seconds (e.g. 300 = 5 min)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matches without updating DB or marking emails seen",
    )
    args = parser.parse_args()

    dry_run = args.dry_run or not gmail_configured()

    if args.loop:
        if not gmail_configured() and not args.dry_run:
            print(SETUP_INSTRUCTIONS, file=sys.stderr)
            return 1
        run_loop(args.loop, dry_run=dry_run)
        return 0

    result = check_inbox(dry_run=dry_run)
    print(format_check_summary(result))
    return 0 if not result.error or result.error == "credentials_missing" else 1


if __name__ == "__main__":
    raise SystemExit(main())