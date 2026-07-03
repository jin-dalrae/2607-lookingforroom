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
from db import get_listing_by_url, init_db, upsert_listing
from facebook_session import login_instructions, run_interactive_login, session_configured, state_path

ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")
PRICE_RE = re.compile(r"\$\s*([\d,]+)")
DETAIL_DELAY_SEC = 0.8
SEARCH_SCROLLS = 10
SEARCH_SCROLL_PAUSE_MS = 1200
JUNK_TITLES = frozenset(
    {
        "",
        "notifications",
        "notification",
        "marketplace",
        "facebook",
        "messenger",
        "see more",
        "filters",
        "create new listing",
        "your listings",
    }
)


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


def _is_junk_title(title: str) -> bool:
    return (title or "").strip().lower() in JUNK_TITLES


def _parse_card_text(text: str) -> tuple[str, int | None]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    price = _parse_price(text)
    title = ""
    for line in lines:
        low = line.lower()
        if low in JUNK_TITLES or low.startswith("http"):
            continue
        if line.startswith("$") and PRICE_RE.search(line):
            continue
        if len(line) > 3:
            title = line
            break
    if not title or _is_junk_title(title):
        for line in lines:
            if not _is_junk_title(line) and len(line) > 3 and not line.startswith("$"):
                title = line
                break
    if not title or _is_junk_title(title):
        title = "Facebook Marketplace listing"
    return title[:200], price


def _playwright_context(playwright: Any, *, headless: bool = True) -> Any:
    if not session_configured():
        raise RuntimeError(login_instructions())
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(state_path()))
    return browser, context


def _scroll_search_results(page: Any) -> None:
    for _ in range(SEARCH_SCROLLS):
        page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 900) * 1.1)")
        page.wait_for_timeout(SEARCH_SCROLL_PAUSE_MS)


def _extract_cards_from_search(page: Any, area_name: str) -> list[FacebookCard]:
    page.wait_for_timeout(2500)
    _scroll_search_results(page)

    raw_items = page.evaluate(
        """() => {
          const seen = new Set();
          const out = [];
          for (const anchor of document.querySelectorAll('a[href*="/marketplace/item/"]')) {
            const href = anchor.href || anchor.getAttribute('href') || '';
            const match = href.match(/\\/marketplace\\/item\\/(\\d+)/);
            if (!match) continue;
            const url = `https://www.facebook.com/marketplace/item/${match[1]}/`;
            if (seen.has(url)) continue;
            seen.add(url);
            out.push({ url, text: (anchor.innerText || '').trim() });
          }
          return out;
        }"""
    )

    cards: list[FacebookCard] = []
    seen: set[str] = set()
    for item in raw_items or []:
        url = _normalize_item_url(str(item.get("url") or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        title, price = _parse_card_text(str(item.get("text") or ""))
        cards.append(
            FacebookCard(
                url=url,
                title=title,
                price=price,
                neighborhood=f"Facebook · {area_name}",
                listing_id=_listing_id_from_url(url),
            )
        )
    return cards


def fetch_search_results(page: Any, search_url: str, area_name: str) -> list[FacebookCard]:
    page.goto(search_url, wait_until="domcontentloaded", timeout=90_000)
    return _extract_cards_from_search(page, area_name)


def _meta_content(page: Any, prop: str) -> str:
    try:
        value = page.locator(f'meta[property="{prop}"]').first.get_attribute("content")
        return (value or "").strip()
    except Exception:
        return ""


def fetch_listing_details(page: Any, url: str) -> dict[str, Any]:
    """Fetch title, price, description from a Marketplace item page."""
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2000)

    title = _meta_content(page, "og:title")
    description = _meta_content(page, "og:description")

    if not title or _is_junk_title(title):
        for selector in ('[data-testid="marketplace-pdp-title"]', "h1"):
            try:
                loc = page.locator(selector).first
                if loc.count():
                    candidate = loc.inner_text(timeout=3000).strip()
                    if candidate and not _is_junk_title(candidate):
                        title = candidate
                        break
            except Exception:
                continue

    if not title or _is_junk_title(title):
        try:
            page_title = (page.title() or "").split("|")[0].strip()
            if page_title and not _is_junk_title(page_title):
                title = page_title
        except Exception:
            title = "Facebook Marketplace listing"

    from locations import clean_listing_description, resolve_neighborhood_from_text

    body_text = description
    if not body_text:
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""

    price = _parse_price(body_text) or _parse_price(title) or _parse_price(description)
    raw_description = description or body_text[:4000] or None
    description = clean_listing_description(raw_description)

    neighborhood = resolve_neighborhood_from_text(
        title=title,
        description=raw_description or "",
        fallback="Facebook Marketplace",
    )

    if _is_junk_title(title):
        title = "Facebook Marketplace listing"

    return {
        "listing_id": _listing_id_from_url(url),
        "url": _normalize_item_url(url) or url,
        "title": title[:200],
        "price": price,
        "neighborhood": neighborhood,
        "description": description,
    }


def _merge_card_and_details(card: FacebookCard, details: dict[str, Any]) -> dict[str, Any]:
    title = details.get("title") or card.title
    if _is_junk_title(title):
        title = card.title
    if _is_junk_title(title):
        title = "Facebook Marketplace listing"
    return {
        "listing_id": details.get("listing_id") or card.listing_id,
        "url": details.get("url") or card.url,
        "title": title,
        "price": details.get("price") or card.price,
        "neighborhood": details.get("neighborhood") or card.neighborhood,
        "description": details.get("description"),
    }


def _needs_detail_fetch(card: FacebookCard) -> bool:
    existing = get_listing_by_url(card.url)
    if existing is None:
        return True
    title = (existing["title"] or "").strip()
    description = (existing["description"] or "").strip()
    if _is_junk_title(title):
        return True
    if len(description) < 40:
        return True
    return False


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


def run_poll_cycle(*, headless: bool = True, with_details: bool = False) -> dict[str, int]:
    from playwright.sync_api import sync_playwright

    init_db()
    counts = {"new": 0, "updated": 0, "unchanged": 0, "errors": 0, "cards": 0, "details": 0}

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
            print(f"Total unique cards: {len(all_cards)}")

            for index, card in enumerate(all_cards, start=1):
                try:
                    fetch_details = with_details and _needs_detail_fetch(card)
                    if fetch_details:
                        if counts["details"] > 0:
                            time.sleep(DETAIL_DELAY_SEC)
                        details = fetch_listing_details(page, card.url)
                        counts["details"] += 1
                        merged = _merge_card_and_details(card, details)
                        outcome = upsert_listing(
                            listing_id=merged["listing_id"],
                            url=merged["url"],
                            title=merged["title"],
                            price=merged["price"],
                            neighborhood=merged["neighborhood"],
                            description=merged["description"],
                            source="facebook",
                        )
                    else:
                        outcome = upsert_listing(
                            listing_id=card.listing_id,
                            url=card.url,
                            title=card.title,
                            price=card.price,
                            neighborhood=card.neighborhood,
                            description=None,
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
    poll.add_argument(
        "--with-details",
        action="store_true",
        help="Fetch each listing page (slow; usually unnecessary)",
    )

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
            import filter as listing_filter
            import rank as rank_module

            print(
                f"{details['outcome']}: {details['title']} "
                f"${details.get('price') or '?'} — {details['url']}"
            )
            print("▶ Filter + rank…")
            listing_filter.run()
            rank_module.run()
            print("Run: python apply.py", details["url"])
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.command == "poll":
        if not session_configured():
            print(login_instructions(), file=sys.stderr)
            return 1
        try:
            counts = run_poll_cycle(
                headless=not args.headed,
                with_details=args.with_details,
            )
            total = counts["new"] + counts["updated"] + counts["unchanged"]
            print(
                f"Done. {counts['cards']} cards → {total} stored "
                f"({counts['new']} new, {counts['updated']} updated, "
                f"{counts['unchanged']} unchanged; "
                f"{counts['details']} detail fetches)"
            )
            if counts["errors"]:
                print(f"Errors: {counts['errors']}", file=sys.stderr)
            if total:
                import filter as listing_filter
                import rank as rank_module

                print("▶ Filter + rank for Facebook listings…")
                listing_filter.run()
                rank_module.run()
            return 0 if total or counts["cards"] == 0 else 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())