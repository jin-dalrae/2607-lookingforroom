#!/usr/bin/env python3
"""Prune to-apply / applied listings whose public post is no longer available."""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import threading
import time
from typing import Any

import requests

from lfr.db import get_connection, init_db
from lfr.db.applications import get_application_by_listing_id, mark_application_rejected

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Application statuses that map to queue "to apply" / "applied".
# Leave replied / visited / skipped / accepted alone.
PRUNE_STATUSES = frozenset({None, "draft", "sent"})

# Per-host polite spacing so Craigslist does not 403-block mid-run.
_HOST_LOCK = threading.Lock()
_HOST_NEXT_OK: dict[str, float] = {}
_DEFAULT_GAP_SEC = {
    "craigslist.org": 0.45,
    "facebook.com": 0.35,
    "zillow.com": 0.25,
}

DELETED_PATTERNS = [
    re.compile(r"this posting has been deleted", re.IGNORECASE),
    re.compile(r"this posting has expired", re.IGNORECASE),
    re.compile(r"posting deleted", re.IGNORECASE),
    re.compile(r"flagged for removal", re.IGNORECASE),
    re.compile(r"this content isn.?t available", re.IGNORECASE),
    re.compile(r"content isn.?t available right now", re.IGNORECASE),
    re.compile(r"listing is no longer available", re.IGNORECASE),
    re.compile(r"this home is off market", re.IGNORECASE),
    re.compile(r"posting has been removed", re.IGNORECASE),
    re.compile(r"this page isn.?t available", re.IGNORECASE),
    re.compile(r"we couldn.?t find that page", re.IGNORECASE),
    re.compile(r"listing not found", re.IGNORECASE),
    re.compile(r"this listing is unavailable", re.IGNORECASE),
    re.compile(r"sorry, this listing is no longer available", re.IGNORECASE),
    # Keep "no longer available" but require listing/posting context to avoid
    # false positives on generic site pages.
    re.compile(
        r"(?:this\s+)?(?:listing|posting|ad|home)\s+(?:is\s+)?no longer available",
        re.IGNORECASE,
    ),
]

# Login / soft walls — do not treat as dead.
ALIVE_BUT_BLOCKED_PATTERNS = [
    re.compile(r"log\s*in\s*to\s*continue", re.IGNORECASE),
    re.compile(r"you must log in", re.IGNORECASE),
    re.compile(r"create\s*(a\s*)?new\s*account", re.IGNORECASE),
    re.compile(r"checkpoint", re.IGNORECASE),
    re.compile(r"<title>\s*blocked\s*</title>", re.IGNORECASE),
    re.compile(r"unusual traffic", re.IGNORECASE),
    re.compile(r"are you a human", re.IGNORECASE),
]


def _host_key(url: str) -> str:
    try:
        host = requests.utils.urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    # Collapse CL city subdomains → craigslist.org
    if host.endswith("craigslist.org"):
        return "craigslist.org"
    if host.endswith("facebook.com"):
        return "facebook.com"
    if host.endswith("zillow.com"):
        return "zillow.com"
    return host


def _throttle(url: str) -> None:
    key = _host_key(url)
    gap = _DEFAULT_GAP_SEC.get(key, 0.2)
    with _HOST_LOCK:
        now = time.monotonic()
        ready = _HOST_NEXT_OK.get(key, 0.0)
        wait = ready - now
        _HOST_NEXT_OK[key] = max(now, ready) + gap
    if wait > 0:
        time.sleep(wait)


def page_indicates_unavailable(
    *,
    status_code: int,
    text: str,
    url: str,
    source: str,
) -> bool:
    """Pure HTML/status check used by HTTP prune and scout detail fetches."""
    final_url = (url or "").lower()
    body = text or ""
    source_l = (source or "").lower()
    title_m = re.search(r"<title>(.*?)</title>", body, flags=re.I | re.S)
    title = (title_m.group(1) if title_m else "").strip().lower()

    if status_code == 404:
        return True
    if status_code in (401, 403, 429):
        return False
    if status_code >= 500:
        return False
    if title in {"blocked", "attention required", "just a moment..."}:
        return False

    for pattern in ALIVE_BUT_BLOCKED_PATTERNS:
        if pattern.search(body):
            return False

    if source_l == "facebook":
        if "marketplace/item" not in final_url:
            if any(p.search(body) for p in DELETED_PATTERNS):
                return True
            if "login" in final_url or "checkpoint" in final_url:
                return False
            if any(
                phrase in body.lower()
                for phrase in (
                    "isn't available",
                    "isnt available",
                    "content not found",
                    "this page isn't available",
                )
            ):
                return True
            return False

    if source_l == "zillow":
        if any(
            frag in final_url
            for frag in (
                "/terms-of-use",
                "/fair-housing",
                "/z/terms",
                "/corp/",
                "/corporate/",
                "privacy",
            )
        ):
            return True

    for pattern in DELETED_PATTERNS:
        if pattern.search(body):
            return True

    return False


def is_url_dead(url: str, source: str) -> bool:
    """Return True only when the listing page clearly indicates unavailable."""
    if not url or not str(url).startswith("http"):
        return False
    try:
        _throttle(url)
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        res = session.get(url, timeout=12, allow_redirects=True)
        return page_indicates_unavailable(
            status_code=res.status_code,
            text=res.text or "",
            url=res.url or url,
            source=source,
        )
    except requests.RequestException:
        # Network blips should not delete listings.
        return False
    except Exception:
        return False


def check_listing(row: dict[str, Any]) -> tuple[str, bool]:
    listing_id = row["id"]
    url = row["url"]
    source = row.get("source") or "craigslist"
    return listing_id, is_url_dead(url, source)


def _fetch_prune_candidates() -> list[dict[str, Any]]:
    """Listings still in to-apply (no app / draft) or applied (sent)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.id, l.url, l.source, a.status AS app_status
            FROM listings l
            LEFT JOIN applications a ON a.listing_id = l.id
            WHERE l.url IS NOT NULL
              AND TRIM(l.url) != ''
              AND (
                a.status IS NULL
                OR a.status = 'draft'
                OR a.status = 'sent'
              )
            ORDER BY l.last_seen DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def mark_dead_listing(listing_id: str) -> None:
    """Mark listing gone without wiping an existing user memo when possible."""
    app = get_application_by_listing_id(listing_id)
    existing_notes = (app or {}).get("notes") if app else None
    notes_str = (existing_notes or "").strip()
    if notes_str and notes_str != "system:dead":
        # Keep user memo; export still treats status=rejected as Gone.
        mark_application_rejected(listing_id)
    else:
        mark_application_rejected(listing_id, notes="system:dead")


def prune_unavailable_listings(
    *,
    max_workers: int = 4,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Check to-apply / applied listing URLs and mark unavailable ones rejected.

    Returns counts: checked, pruned, errors.
    """
    init_db()
    listings = _fetch_prune_candidates()
    if limit is not None and limit > 0:
        listings = listings[:limit]

    # Prefer Craigslist first (most reliable deleted-page signal), then others.
    def _source_rank(row: dict[str, Any]) -> int:
        src = (row.get("source") or "").lower()
        if src == "craigslist":
            return 0
        if src == "zillow":
            return 1
        return 2

    listings.sort(key=_source_rank)

    checked = len(listings)
    pruned = 0
    errors = 0

    if not listings:
        return {"checked": 0, "pruned": 0, "errors": 0}

    workers = max(1, min(max_workers, 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_listing = {
            executor.submit(check_listing, listing): listing for listing in listings
        }
        for future in concurrent.futures.as_completed(future_to_listing):
            listing = future_to_listing[future]
            try:
                listing_id, dead = future.result()
                if not dead:
                    continue
                status = listing.get("app_status") or "to_apply"
                label = "applied" if status == "sent" else "to_apply"
                if dry_run:
                    print(f"[dry-run] dead ({label}): {listing['url']}")
                else:
                    print(f"Dead ({label}): {listing['url']} → deleted")
                    mark_dead_listing(listing_id)
                pruned += 1
            except Exception as exc:
                errors += 1
                print(f"Error processing {listing.get('url')}: {exc}", file=sys.stderr)

    return {"checked": checked, "pruned": pruned, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-delete to-apply / applied listings whose post is no longer available"
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report dead URLs without marking them deleted",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max listings to check (default: all candidates)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel HTTP workers (default: 4; keep low to avoid CL blocks)",
    )
    args = parser.parse_args(argv)

    print("Checking to-apply / applied listings for unavailable posts…")
    result = prune_unavailable_listings(
        max_workers=max(1, args.workers),
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(
        f"Checked {result['checked']} · pruned {result['pruned']}"
        + (f" · errors {result['errors']}" if result["errors"] else "")
        + (" (dry-run)" if args.dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
