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
DETAIL_PAGE_TIMEOUT_MS = 25_000
DETAIL_SETTLE_MS = 800
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
    card_text: str = ""
    location_line: str = ""
    listed_phrase: str = ""


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


def is_junk_facebook_title(title: str) -> bool:
    from listing_description import is_junk_facebook_title as _is_junk_fb_title

    return _is_junk_fb_title(title) or _is_junk_title(title)


def _parse_card_text(text: str) -> tuple[str, int | None, str, str]:
    from locations import parse_location_line

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    price = _parse_price(text)
    location_line = ""
    listed_phrase = ""
    title = ""
    title_candidates: list[str] = []

    for line in lines:
        low = line.lower()
        if low in JUNK_TITLES or low.startswith("http"):
            continue
        if line.startswith("$") and PRICE_RE.search(line):
            continue
        if re.search(r"\bago\b$", low) or low in ("today", "yesterday"):
            listed_phrase = line
            continue
        loc = parse_location_line(line)
        if loc:
            location_line = loc
            continue
        if len(line) > 3:
            title_candidates.append(line)

    for candidate in title_candidates:
        if not _is_junk_title(candidate):
            title = candidate
            break
    if not title and title_candidates:
        title = title_candidates[0]
    if not title or _is_junk_title(title):
        title = "Facebook Marketplace listing"
    return title[:200], price, location_line, listed_phrase


def _card_neighborhood(card: FacebookCard) -> str:
    """Prefer the rental city from the search card over the search-feed label."""
    if card.location_line:
        from locations import resolve_neighborhood_from_text

        blob = _card_description_blob(location_line=card.location_line) or ""
        return resolve_neighborhood_from_text(description=blob, fallback=card.location_line)
    return card.neighborhood


def _card_description_blob(
    *,
    location_line: str = "",
    listed_phrase: str = "",
) -> str | None:
    parts: list[str] = []
    if location_line:
        parts.append(f"Rental Location\n{location_line}")
    if listed_phrase:
        phrase = listed_phrase.strip()
        if not phrase.lower().startswith("listed"):
            phrase = f"Listed {phrase}"
        parts.append(phrase)
    return "\n".join(parts) if parts else None


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
        card_text = str(item.get("text") or "")
        title, price, location_line, listed_phrase = _parse_card_text(card_text)
        cards.append(
            FacebookCard(
                url=url,
                title=title,
                price=price,
                neighborhood=area_name,
                listing_id=_listing_id_from_url(url),
                card_text=card_text,
                location_line=location_line,
                listed_phrase=listed_phrase,
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


def _extract_marketplace_body_text(page: Any, og_description: str) -> str:
    """Pull listing description text only — not images or Marketplace chrome."""
    for selector in (
        '[data-testid="marketplace-pdp-description"]',
        '[data-testid="marketplace-pdp-listing-description"]',
    ):
        try:
            loc = page.locator(selector).first
            if loc.count():
                text = loc.inner_text(timeout=3000).strip()
                if len(text) >= 20:
                    return text[:8000]
        except Exception:
            continue

    if og_description and len(og_description) >= 20:
        low = og_description.lower()
        if "marketplace" not in low[:40] and "notification" not in low:
            return og_description[:8000]

    try:
        text = page.evaluate(
            """() => {
              const stop = /seller information|today's picks|send seller a message|marketplace access|browse all/i;
              for (const sel of [
                '[data-testid="marketplace-pdp-description"]',
                '[data-testid="marketplace-pdp-listing-description"]',
              ]) {
                for (const el of document.querySelectorAll(sel)) {
                  const t = (el.innerText || '').trim();
                  if (t.length >= 20) return t.slice(0, 8000);
                }
              }
              const body = (document.body && document.body.innerText) || '';
              const cut = body.search(stop);
              const head = cut > 80 ? body.slice(0, cut) : body;
              const lines = head.split('\\n').map((l) => l.trim()).filter(Boolean);
              const skip = /^(marketplace|notifications?|inbox|buying|selling|location|categories|vehicles|apparel|free stuff|home goods|musical|office supplies|pet supplies|property rentals|within \\d+ mi|edit marketplace)/i;
              const kept = [];
              for (const line of lines) {
                if (skip.test(line)) continue;
                if (/^\\$[\\d,]+$/.test(line)) continue;
                if (/^joined facebook/i.test(line)) break;
                kept.push(line);
              }
              return kept.join('\\n').slice(0, 8000);
            }"""
        )
        if text and len(str(text).strip()) >= 20:
            return str(text).strip()[:8000]
    except Exception:
        pass

    return (og_description or "")[:8000]


def _extract_labeled_value_from_page(page: Any, labels: tuple[str, ...]) -> str:
    """Read the line after a Marketplace PDP label (e.g. Rental location, Availability)."""
    try:
        value = page.evaluate(
            """(labels) => {
              const wanted = labels.map((l) => l.toLowerCase());
              const body = (document.body && document.body.innerText) || '';
              const lines = body.split('\\n').map((l) => l.trim()).filter(Boolean);
              for (let i = 0; i < lines.length; i++) {
                const low = lines[i].toLowerCase();
                if (wanted.includes(low) && lines[i + 1]) {
                  return lines[i + 1];
                }
              }
              for (const el of document.querySelectorAll('span, div')) {
                const t = (el.innerText || '').trim();
                if (!t) continue;
                if (!wanted.includes(t.toLowerCase())) continue;
                const parent = el.parentElement;
                if (!parent) continue;
                const parts = (parent.innerText || '').split('\\n').map((l) => l.trim()).filter(Boolean);
                const idx = parts.findIndex((p) => wanted.includes(p.toLowerCase()));
                if (idx >= 0 && parts[idx + 1]) return parts[idx + 1];
              }
              return '';
            }""",
            list(labels),
        )
        return str(value or "").strip()
    except Exception:
        return ""


def _extract_rental_location_from_page(page: Any) -> str:
    """Read the Rental location field from a Marketplace item page."""
    from locations import is_junk_location_line, parse_location_line

    candidate = _extract_labeled_value_from_page(page, ("Rental location",))
    if candidate and not is_junk_location_line(candidate):
        return (parse_location_line(candidate) or candidate).strip()
    return ""


def _extract_move_in_from_page(page: Any) -> str:
    """Read availability / move-in from a Marketplace rental PDP."""
    from listing_move_in import is_boilerplate_move_in_phrase

    for label_group in (
        ("Availability", "Available", "Date available"),
        ("Move-in date", "Move in date"),
    ):
        candidate = _extract_labeled_value_from_page(page, label_group)
        if not candidate or len(candidate) > 80:
            continue
        if is_boilerplate_move_in_phrase(candidate):
            continue
        return candidate
    return ""


def _compose_facebook_description(
    *,
    rental_address: str = "",
    move_in_phrase: str = "",
    body_text: str | None = None,
) -> str | None:
    """Keep structured PDP fields even when the post body is Marketplace chrome."""
    parts: list[str] = []
    if rental_address:
        parts.append(f"Rental Location\n{rental_address}")
    if move_in_phrase:
        parts.append(f"Availability\n{move_in_phrase}")
    if body_text:
        parts.append(body_text.strip())
    return "\n\n".join(parts) if parts else None


def _prepare_detail_page(page: Any) -> None:
    """Skip images/media so detail fetches stay text-only and faster."""

    def _route_handler(route: Any) -> None:
        if route.request.resource_type in ("image", "media", "font"):
            route.abort()
        else:
            route.continue_()

    try:
        page.route("**/*", _route_handler)
    except Exception:
        pass


def fetch_listing_details(page: Any, url: str) -> dict[str, Any]:
    """Fetch title, price, description from a Marketplace item page."""
    page.goto(url, wait_until="domcontentloaded", timeout=DETAIL_PAGE_TIMEOUT_MS)
    page.wait_for_timeout(DETAIL_SETTLE_MS)

    title = _meta_content(page, "og:title")
    description = _meta_content(page, "og:description")

    if not title or _is_junk_title(title):
        for selector in ('[data-testid="marketplace-pdp-title"]', "h1"):
            try:
                loc = page.locator(selector).first
                if loc.count():
                    candidate = loc.inner_text(timeout=1500).strip()
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

    from listing_dates import parse_posted_at
    from locations import (
        clean_listing_description,
        parse_facebook_listing_fields,
        resolve_neighborhood_from_text,
    )

    body_text = _extract_marketplace_body_text(page, description)
    price = _parse_price(body_text) or _parse_price(title) or _parse_price(description)
    page_rental_location = _extract_rental_location_from_page(page)
    page_move_in = _extract_move_in_from_page(page)

    body_clean = clean_listing_description(body_text or description or None)
    raw_description = _compose_facebook_description(
        rental_address=page_rental_location,
        move_in_phrase=page_move_in,
        body_text=body_clean,
    )

    fb_fields = parse_facebook_listing_fields(raw_description or "")
    rental_address = fb_fields.get("rental_address") or page_rental_location or ""
    if rental_address and raw_description and "rental location" not in raw_description.lower():
        raw_description = _compose_facebook_description(
            rental_address=rental_address,
            move_in_phrase=page_move_in,
            body_text=body_clean,
        )
        fb_fields = parse_facebook_listing_fields(raw_description or "")

    description = raw_description
    rental_address = fb_fields.get("rental_address") or rental_address
    neighborhood = resolve_neighborhood_from_text(
        title=title,
        description=raw_description or "",
        fallback=fb_fields.get("display_place") or "Unknown",
    )

    if is_junk_facebook_title(title):
        title = "Facebook Marketplace listing"

    posted_at = parse_posted_at(body_text or raw_description or "")

    from listing_move_in import resolve_move_in_date_storage

    move_in_date = resolve_move_in_date_storage(
        {
            "title": title,
            "description": raw_description,
            "move_in_date": None,
            "first_seen": None,
            "last_seen": None,
        }
    )

    return {
        "listing_id": _listing_id_from_url(url),
        "url": _normalize_item_url(url) or url,
        "title": title[:200],
        "price": price,
        "neighborhood": neighborhood,
        "rental_address": rental_address or None,
        "description": description,
        "move_in_date": move_in_date or None,
        "posted_at": posted_at,
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
        "posted_at": details.get("posted_at"),
        "rental_address": details.get("rental_address"),
        "move_in_date": details.get("move_in_date"),
    }


def _needs_detail_fetch(card: FacebookCard) -> bool:
    from listing_description import needs_description_backfill

    existing = get_listing_by_url(card.url)
    if existing is None:
        return True
    if _is_junk_title((existing.get("title") or "").strip()):
        return True
    if needs_description_backfill(existing):
        return True
    if not (existing.get("rental_address") or "").strip():
        return True
    hood = (existing.get("neighborhood") or "").lower()
    if hood.startswith("facebook") or "marketplace" in hood:
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
        move_in_date=details.get("move_in_date"),
        posted_at=details.get("posted_at"),
        rental_address=details.get("rental_address"),
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
            seen_urls: set[str] = set()
            detail_page = context.new_page()

            for area_name, search_url in FACEBOOK_MARKETPLACE_SEARCHES:
                print(f"Facebook Marketplace: {area_name}")
                search_page = context.new_page()
                try:
                    cards = fetch_search_results(search_page, search_url, area_name)
                except Exception as exc:
                    print(f"  warning: search failed: {exc}", file=sys.stderr)
                    counts["errors"] += 1
                    continue
                finally:
                    search_page.close()

                print(f"  → {len(cards)} listing(s) on search page")
                for card in cards:
                    if card.url in seen_urls:
                        continue
                    seen_urls.add(card.url)
                    counts["cards"] += 1
                    try:
                        existing = get_listing_by_url(card.url)
                        fetch_details = existing is None or (
                            with_details and _needs_detail_fetch(card)
                        )
                        if fetch_details:
                            if counts["details"] > 0:
                                time.sleep(DETAIL_DELAY_SEC)
                            details = fetch_listing_details(detail_page, card.url)
                            counts["details"] += 1
                            merged = _merge_card_and_details(card, details)
                            outcome = upsert_listing(
                                listing_id=merged["listing_id"],
                                url=merged["url"],
                                title=merged["title"],
                                price=merged["price"],
                                neighborhood=merged["neighborhood"],
                                description=merged["description"],
                                move_in_date=merged.get("move_in_date"),
                                posted_at=merged.get("posted_at"),
                                rental_address=merged.get("rental_address"),
                                source="facebook",
                            )
                        else:
                            from listing_dates import parse_posted_at

                            card_description = _card_description_blob(
                                location_line=card.location_line,
                                listed_phrase=card.listed_phrase,
                            )
                            outcome = upsert_listing(
                                listing_id=card.listing_id,
                                url=card.url,
                                title=card.title,
                                price=card.price,
                                neighborhood=_card_neighborhood(card),
                                description=card_description,
                                posted_at=parse_posted_at(card_description or card.card_text or ""),
                                rental_address=card.location_line or None,
                                source="facebook",
                            )
                        counts[outcome] += 1
                    except Exception as exc:
                        counts["errors"] += 1
                        print(f"  warning: {card.url}: {exc}", file=sys.stderr)

            detail_page.close()
            print(f"Total unique cards: {counts['cards']}")
        finally:
            context.close()
            browser.close()

    return counts


def refetch_junk_titles(*, limit: int | None = None, headless: bool = True) -> dict[str, int]:
    """Re-fetch Facebook listings stuck with placeholder titles."""
    from playwright.sync_api import sync_playwright

    from db import get_connection, init_db, upsert_listing

    init_db()
    query = """
        SELECT url FROM listings
        WHERE source = 'facebook'
          AND (
              lower(trim(coalesce(title, ''))) IN (
                  'notifications', 'notification', 'facebook marketplace listing'
              )
              OR lower(title) LIKE '%marketplace -%'
              OR lower(title) LIKE '%(1) marketplace%'
              OR lower(title) LIKE '%(2) marketplace%'
          )
        ORDER BY last_seen DESC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    counts = {"updated": 0, "unchanged": 0, "errors": 0, "total": len(rows)}
    if not rows:
        return counts

    if not session_configured():
        raise RuntimeError(login_instructions())

    with sync_playwright() as playwright:
        browser, context = _playwright_context(playwright, headless=headless)
        try:
            page = context.new_page()
            for index, row in enumerate(rows, start=1):
                url = str(row["url"])
                try:
                    if index > 1:
                        time.sleep(DETAIL_DELAY_SEC)
                    details = fetch_listing_details(page, url)
                    title = (details.get("title") or "").strip()
                    if is_junk_facebook_title(title):
                        counts["unchanged"] += 1
                        continue
                    from db import delete_score

                    delete_score(details["listing_id"])
                    outcome = upsert_listing(
                        listing_id=details["listing_id"],
                        url=details["url"],
                        title=details["title"],
                        price=details.get("price"),
                        neighborhood=details.get("neighborhood"),
                        description=details.get("description"),
                        move_in_date=details.get("move_in_date"),
                        posted_at=details.get("posted_at"),
                        rental_address=details.get("rental_address"),
                        source="facebook",
                    )
                    if outcome == "updated":
                        counts["updated"] += 1
                    else:
                        counts["unchanged"] += 1
                    print(f"  [{index}/{len(rows)}] {outcome}: {title[:80]}")
                except Exception as exc:
                    counts["errors"] += 1
                    print(f"  warning: {url}: {exc}", file=sys.stderr)
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
        help="Also re-fetch existing listings missing location or description (new listings always get one detail fetch)",
    )

    ingest = sub.add_parser("ingest", help="Import one Marketplace item URL")
    ingest.add_argument("url", help="facebook.com/marketplace/item/… URL")
    ingest.add_argument("--headed", action="store_true")

    fix = sub.add_parser("fix-titles", help="Re-fetch junk Facebook titles (e.g. Notifications)")
    fix.add_argument("--headed", action="store_true")
    fix.add_argument("--limit", type=int, default=None)

    backfill = sub.add_parser(
        "backfill",
        help="Fetch Facebook detail pages for rows missing location or description",
    )
    backfill.add_argument("--headed", action="store_true")
    backfill.add_argument("--limit", type=int, default=50)
    backfill.add_argument(
        "--all",
        action="store_true",
        help="Backfill any Facebook row needing details, not only queue listings",
    )

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

    if args.command == "fix-titles":
        if not session_configured():
            print(login_instructions(), file=sys.stderr)
            return 1
        try:
            counts = refetch_junk_titles(
                limit=args.limit,
                headless=not args.headed,
            )
            print(
                f"Done. {counts['total']} junk title(s): "
                f"{counts['updated']} updated, {counts['unchanged']} unchanged, "
                f"{counts['errors']} errors"
            )
            if counts["updated"]:
                import filter as listing_filter

                listing_filter.run(rescore_all=True, use_gemini=False)
            return 0 if not counts["errors"] else 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.command == "backfill":
        if not session_configured():
            print(login_instructions(), file=sys.stderr)
            return 1
        try:
            from db import backfill_facebook_details, purge_premature_facebook_scores

            purged = purge_premature_facebook_scores()
            if purged:
                print(f"Cleared {purged} premature Facebook score(s).")
            stats = backfill_facebook_details(
                limit=args.limit,
                queue_only=not args.all,
            )
            print(
                f"Done. fetched={stats['fetched']} updated={stats['updated']} "
                f"unchanged={stats['unchanged']} errors={stats['errors']} "
                f"rescored={stats.get('rescored', 0)}"
            )
            if stats.get("rescored", 0) or stats.get("updated", 0):
                import filter as listing_filter

                listing_filter.run()
            return 0 if not stats["errors"] else 1
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