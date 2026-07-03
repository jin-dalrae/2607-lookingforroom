#!/usr/bin/env python3
"""Facebook Marketplace scout via Playwright (requires local login once)."""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from config import FACEBOOK_MARKETPLACE_SEARCHES, SEARCH_CRITERIA
from db import init_db, upsert_listing
from facebook_session import login_instructions, run_interactive_login, session_configured, state_path

ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")
PRICE_RE = re.compile(r"\$\s*([\d,]+)")
DETAIL_DELAY_SEC = 1.5


@dataclass
class FacebookCard:
    url: str
    title: str
    price: int | None
    neighborhood: str
    listing_id: str


def _normalize_item_url(href: str) -> str | None:
    href = (href or "").strip()
    if not href:
        return None
    if href.startswith("/"):
        href = f"https://www.facebook.com{href}"
    if "/marketplace/item/" not in href:
        return None
    parsed = urlparse(href)
    path = parsed.path.rstrip("/")
    match = ITEM_ID_RE.search(path)
    if not match:
        return None
    item_id = match.group(1)
    return f"https://www.facebook.com/marketplace/item/{item_id}/"


def _listing_id_from_url(url: str) -> str:
    match = ITEM_ID_RE.search(url)
    if match:
        return f"fb-{match.group(1)}"
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return f"fb-{slug}" if slug else url


def _parse_price(text: str) -> int | None:
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    digits = match.group(1).replace(",", "")
    try:
        value = int(digits)
    except ValueError:
        return None
    cap = SEARCH_CRITERIA.get("price_match_max", SEARCH_CRITERIA["max_rent"])
    if value > cap:
        return value
    return value


def _playwright_context(playwright: Any, *, headless: bool = True) -> Any:
    if not session_configured():
        raise RuntimeError(login_instructions())
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(state_path()))
    return browser, context


def _extract_cards_from_search(page: Any, area_name: str) -> list[FacebookCard]:
    page.wait_for_timeout(3000)
    cards: list[FacebookCard] = []
    seen: set[str] = set()

    for anchor in page.locator('a[href*="/marketplace/item/"]').all():
        href = anchor.get_attribute("href") or ""
        url = _normalize_item_url(href)
        if not url or url in seen:
            continue
        seen.add(url)

        try:
            text = anchor.inner_text(timeout=2000).strip()
        except Exception:
            text = ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        title = lines[0] if lines else "Facebook Marketplace listing"
        price = _parse_price(text)

        cards.append(
            FacebookCard(
                url=url,
                title=title[:200],
                price=price,
                neighborhood=f"Facebook · {area_name}",
                listing_id=_listing_id_from_url(url),
            )
        )

    return cards


def fetch_search_results(page: Any, search_url: str, area_name: str) -> list[FacebookCard]:
    page.goto(search_url, wait_until="domcontentloaded", timeout=90_000)
    return _extract_cards_from_search(page, area_name)


def fetch_listing_details(page: Any, url: str) -> dict[str, Any]:
    """Fetch title, price, description from a Marketplace item page."""
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)

    title = ""
    for selector in ("h1", '[data-testid="marketplace-pdp-title"]'):
        try:
            loc = page.locator(selector).first
            if loc.count():
                title = loc.inner_text(timeout=3000).strip()
                if title:
                    break
        except Exception:
            continue

    if not title:
        try:
            title = (page.title() or "").split("|")[0].strip()
        except Exception:
            title = "Facebook Marketplace listing"

    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body_text = ""

    price = _parse_price(body_text) or _parse_price(title)
    description = body_text[:4000] if body_text else ""

    neighborhood = "Facebook Marketplace"
    for label in ("San Francisco", "Oakland", "Berkeley", "SOMA", "Mission"):
        if label.lower() in body_text.lower():
            neighborhood = f"Facebook · {label}"
            break

    return {
        "listing_id": _listing_id_from_url(url),
        "url": _normalize_item_url(url) or url,
        "title": title[:200],
        "price": price,
        "neighborhood": neighborhood,
        "description": description or None,
    }


def ingest_url(url: str, *, headless: bool = True) -> dict[str, Any]:
    """Fetch one Marketplace listing and store in DB."""
    from playwright.sync_api import sync_playwright

    init_db()
    normalized = _normalize_item_url(url) or url.strip()
    if "/marketplace/item/" not in normalized:
        raise ValueError("Not a Facebook Marketplace item URL")

    with sync_playwright() as playwright:
        browser, context = _playwright_context(playwright, headless=headless)
        try:
            page = context.new_page()
            details = fetch_listing_details(page, normalized)
        finally:
            context.close()
            browser.close()

    outcome = upsert_listing(
        listing_id=details["listing_id"],
        url=details["url"],
        title=details["title"],
        price=details["price"],
        neighborhood=details["neighborhood"],
        description=details["description"],
        source="facebook",
    )
    details["outcome"] = outcome
    return details


def run_poll_cycle(*, headless: bool = True) -> dict[str, int]:
    from playwright.sync_api import sync_playwright

    init_db()
    counts = {"new": 0, "updated": 0, "unchanged": 0, "errors": 0, "cards": 0}

    with sync_playwright() as playwright:
        browser, context = _playwright_context(playwright, headless=headless)
        try:
            page = context.new_page()
            seen_urls: set[str] = set()
            all_cards: list[FacebookCard] = []

            for area_name, search_url in FACEBOOK_MARKETPLACE_SEARCHES:
                print(f"Facebook Marketplace: {area_name}")
                try:
                    cards = fetch_search_results(page, search_url, area_name)
                except Exception as exc:
                    print(f"  warning: search failed: {exc}", file=sys.stderr)
                    counts["errors"] += 1
                    continue
                print(f"  → {len(cards)} listing(s) on search page")
                for card in cards:
                    if card.url not in seen_urls:
                        seen_urls.add(card.url)
                        all_cards.append(card)

            counts["cards"] = len(all_cards)

            for index, card in enumerate(all_cards, start=1):
                if index > 1:
                    time.sleep(DETAIL_DELAY_SEC)
                try:
                    details = fetch_listing_details(page, card.url)
                    outcome = upsert_listing(
                        listing_id=details["listing_id"],
                        url=details["url"],
                        title=details["title"] or card.title,
                        price=details["price"] or card.price,
                        neighborhood=details["neighborhood"] or card.neighborhood,
                        description=details["description"],
                        source="facebook",
                    )
                    counts[outcome] += 1
                except Exception as exc:
                    counts["errors"] += 1
                    print(f"  warning: {card.url}: {exc}", file=sys.stderr)
        finally:
            context.close()
            browser.close()

    return counts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Facebook Marketplace room scout")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Open browser to log in and save session")

    poll = sub.add_parser("poll", help="Poll configured Marketplace searches")
    poll.add_argument("--headed", action="store_true", help="Show browser window")

    ingest = sub.add_parser("ingest", help="Import one Marketplace item URL")
    ingest.add_argument("url", help="facebook.com/marketplace/item/… URL")
    ingest.add_argument("--headed", action="store_true")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "login":
        try:
            run_interactive_login()
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.command == "ingest":
        try:
            details = ingest_url(args.url, headless=not args.headed)
            print(
                f"{details['outcome']}: {details['title']} "
                f"${details.get('price') or '?'} — {details['url']}"
            )
            print("Run: python filter.py && python rank.py")
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.command == "poll":
        if not session_configured():
            print(login_instructions(), file=sys.stderr)
            return 1
        try:
            counts = run_poll_cycle(headless=not args.headed)
            total = counts["new"] + counts["updated"] + counts["unchanged"]
            print(
                f"Done. {counts['cards']} cards → {total} stored "
                f"({counts['new']} new, {counts['updated']} updated, "
                f"{counts['unchanged']} unchanged)"
            )
            if counts["errors"]:
                print(f"Errors: {counts['errors']}", file=sys.stderr)
            return 0 if total or counts["cards"] == 0 else 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())