#!/usr/bin/env python3
"""Zillow scouter via HasData Listing API (Playwright fallback)."""

from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
import requests

from lfr.config import (
    HASDATA_API_KEY,
    SEARCH_CRITERIA,
    ZILLOW_SEARCHES,
    zillow_api_searches,
)
from lfr.db import init_db, upsert_listing
from lfr.listings.layout import detect_layout

PRICE_RE = re.compile(r"\$\s*([\d,]+)")
HASDATA_LISTING_URL = "https://api.hasdata.com/scrape/zillow/listing"
LEGACY_LISTING_URL = "https://api.scrape-it.cloud/zillow/listing"
MAX_PAGES = 2
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class ZillowCard:
    url: str
    title: str
    price: int | None
    neighborhood: str
    listing_id: str
    description: str = ""
    rental_address: str = ""
    beds: int | None = None
    baths: int | None = None


def _parse_price(text: str) -> int | None:
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


# A Zillow result under /apartments/ or /b/ may be either a real unit inside a
# complex (concrete price + real unit number) or a building shell with no price
# of its own. The URL does not tell them apart — the price does.
#
# Separately, Zillow's rental-network feed emits synthetic unit ids for
# floor-plan entries ("765 Geary St #C25628efa"), where the price is the plan's
# starting rate rather than one unit's rent. Real unit numbers are short and
# numeric ("#209", "APT 10", "#51").
_SYNTHETIC_UNIT_RE = re.compile(
    r"(?:#|\bapt\b|\bunit\b|\bste\b)\s*([A-Za-z0-9]{6,})\s*$", re.IGNORECASE
)

# "$1,500+", "From $1,500", "$1,500 - $3,200" — none of these is a rent we can
# trust for one unit. _to_int() would happily turn them into a clean-looking
# number ("$1,500 - $3,200" strips to 15003200; "$1,500+" to 1500).
_PRICE_RANGE_RE = re.compile(r"\$?\s*[\d,]+\s*(?:-|\u2013|\u2014|to)\s*\$?\s*[\d,]+", re.IGNORECASE)
_PRICE_VAGUE_RE = re.compile(r"\bfrom\b|\bstarting\b|\d\s*\+", re.IGNORECASE)


def _has_synthetic_unit(street: str) -> bool:
    match = _SYNTHETIC_UNIT_RE.search(str(street or "").strip())
    if not match:
        return False
    token = match.group(1)
    # Long *and* containing letters — a plain long number is still a real unit.
    return len(token) >= 6 and any(ch.isalpha() for ch in token)


def _price_is_vague(value: Any) -> bool:
    """True when the price text describes a range or a 'from' teaser."""
    if value is None or isinstance(value, (int, float, bool)):
        return False
    text = str(value)
    return bool(_PRICE_RANGE_RE.search(text) or _PRICE_VAGUE_RE.search(text))


def _extract_id_from_url(url: str) -> str:
    match = re.search(r"homedetails/([A-Za-z0-9_-]+)_zpid", url)
    if match:
        return f"z-{match.group(1)}"
    zpid = re.search(r"/(\d+)_zpid", url or "")
    if zpid:
        return f"z-{zpid.group(1)}"
    h = hashlib.md5((url or "").encode("utf-8")).hexdigest()[:12]
    return f"z-{h}"


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    if not digits:
        return None
    try:
        return int(float(digits))
    except ValueError:
        return None


def is_interactive() -> bool:
    return bool(sys.stdin and sys.stdin.isatty())


def _api_key() -> str:
    return (HASDATA_API_KEY or os.getenv("HASDATA_API_KEY") or os.getenv("ZILLOW_API_KEY") or "").strip()


def _search_hasdata(params: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Call HasData Zillow listing API (current host, then legacy SDK host)."""
    headers = {"Content-Type": "application/json", "x-api-key": api_key}
    last_error = None
    for endpoint in (HASDATA_LISTING_URL, LEGACY_LISTING_URL):
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=90)
            payload = response.json() if response.content else {}
        except Exception as exc:
            last_error = exc
            continue
        if response.status_code == 401:
            raise RuntimeError("HasData API key is invalid")
        if response.status_code == 403:
            raise RuntimeError("HasData API credits are exhausted")
        if response.status_code == 429:
            raise RuntimeError("HasData concurrency limit reached — retry shortly")
        if response.status_code >= 400:
            last_error = RuntimeError(
                f"HasData {response.status_code}: {payload if payload else response.text[:200]}"
            )
            continue
        if isinstance(payload, dict):
            return payload
        last_error = RuntimeError("HasData returned a non-object JSON payload")
    if last_error:
        raise last_error
    return {}


def _search_sdk(params: dict[str, Any], api_key: str) -> dict[str, Any] | None:
    try:
        from zillow_api import ZillowAPI
    except ImportError:
        return None
    client = ZillowAPI(api_key)
    return client.search(params=params)


def search_zillow(params: dict[str, Any], api_key: str) -> dict[str, Any]:
    """HasData REST first (current API). The published SDK still hits scrape-it.cloud."""
    try:
        return _search_hasdata(params, api_key)
    except Exception as rest_exc:
        try:
            sdk = _search_sdk(params, api_key)
            if isinstance(sdk, dict) and (sdk.get("properties") or sdk.get("requestMetadata")):
                return sdk
        except Exception:
            pass
        raise rest_exc


def _card_from_property(prop: dict[str, Any], *, max_rent: int) -> ZillowCard | None:
    url = str(prop.get("url") or "").strip()
    if url.startswith("/"):
        url = f"https://www.zillow.com{url}"
    if not url:
        return None

    raw_price = prop.get("price") or prop.get("unformattedPrice")
    if _price_is_vague(raw_price):
        return None
    price = _to_int(raw_price)
    if price is None:
        return None
    if price > max_rent:
        return None

    addr_obj = prop.get("address") if isinstance(prop.get("address"), dict) else {}
    # Prefer the structured address. For units inside a complex, `addressRaw`
    # is prefixed with the building's marketing name ("2300-2312 Market Street
    # (1272rc), 2300-2312 Market St #209, ..."), which does not read as a
    # specific street address downstream, so the queue falls back to just
    # "San Francisco". The structured fields are clean.
    if addr_obj.get("street"):
        address = ", ".join(
            part
            for part in (
                str(addr_obj.get("street") or "").strip(),
                str(addr_obj.get("city") or "").strip(),
                " ".join(
                    p
                    for p in (
                        str(addr_obj.get("state") or "").strip(),
                        str(addr_obj.get("zipcode") or "").strip(),
                    )
                    if p
                ),
            )
            if part
        )
    else:
        address = str(prop.get("addressRaw") or prop.get("address") or "").strip()
    clean_address = " ".join(str(address).split()) or "San Francisco, CA"

    if _has_synthetic_unit(addr_obj.get("street") or clean_address):
        return None

    from lfr.listings.location import is_new_york_location

    state = str(addr_obj.get("state") or "").strip().upper()
    city = str(addr_obj.get("city") or "").strip()
    loc_blob = f"{clean_address} {url} {city} {state}".lower()
    if is_new_york_location(
        primary=loc_blob,
        rental_location=clean_address,
        city=city,
        url=url,
    ):
        return None
    if state and state not in ("CA", "CALIFORNIA"):
        return None
    if "san francisco" not in loc_blob and "san-francisco" not in loc_blob:
        return None

    beds = _to_int(prop.get("beds") or prop.get("bedrooms"))
    baths = _to_int(prop.get("baths") or prop.get("bathrooms"))
    sqft = _to_int(prop.get("area") or prop.get("livingArea") or prop.get("sqft"))
    hood = (
        str(addr_obj.get("city") or "").strip()
        or str(prop.get("neighborhood") or "").strip()
        or "San Francisco"
    )
    zpid = prop.get("id") or prop.get("zpid")
    listing_id = f"z-{zpid}" if zpid else _extract_id_from_url(url)

    layout_bit = ""
    if beds is not None and baths is not None:
        layout_bit = f"{beds} bd {baths} ba"
    elif beds is not None:
        layout_bit = f"{beds} bd"
    title = f"Zillow: {clean_address}"
    if layout_bit:
        title = f"Zillow: {layout_bit} — {clean_address}"

    desc_parts = [clean_address]
    if layout_bit:
        desc_parts.append(layout_bit)
    if sqft:
        desc_parts.append(f"{sqft} sqft")
    if prop.get("homeType"):
        desc_parts.append(str(prop["homeType"]))
    if prop.get("description"):
        desc_parts.append(str(prop["description"])[:2000])
    if prop.get("brokerName"):
        desc_parts.append(f"Listed by {prop['brokerName']}")

    return ZillowCard(
        url=url,
        title=title,
        price=price,
        neighborhood=hood,
        listing_id=str(listing_id),
        description="\n".join(desc_parts),
        rental_address=clean_address,
        beds=beds,
        baths=baths,
    )


def _save_cards(cards: list[ZillowCard], counts: dict[str, int]) -> None:
    for card in cards:
        try:
            result = upsert_listing(
                listing_id=card.listing_id,
                url=card.url,
                title=card.title,
                price=card.price,
                neighborhood=card.neighborhood,
                description=card.description,
                rental_address=card.rental_address,
                source="zillow",
                beds=card.beds,
                baths=card.baths,
            )
            counts[result] = counts.get(result, 0) + 1
        except Exception as exc:
            print(f"Error saving Zillow card {card.listing_id}: {exc}", file=sys.stderr)


def run_poll_cycle_api() -> dict[str, int]:
    init_db()
    counts = {"new": 0, "updated": 0, "unchanged": 0, "errors": 0}
    api_key = _api_key()
    if not api_key:
        print(
            "[zillow] No HasData API key. Set HASDATA_API_KEY in .env "
            "(https://app.hasdata.com/sign-in — free credits on signup)."
        )
        return counts

    max_rent = int(SEARCH_CRITERIA.get("max_rent") or 1500)
    seen_ids: set[str] = set()
    for name, params in zillow_api_searches():
        print(f"Polling Zillow API: {name}…")
        page_cards = 0
        for page in range(1, MAX_PAGES + 1):
            query = dict(params)
            query["page"] = page
            try:
                payload = search_zillow(query, api_key)
            except Exception as exc:
                print(f"  error: {exc}", file=sys.stderr)
                counts["errors"] = counts.get("errors", 0) + 1
                break
            properties = payload.get("properties") or payload.get("listings") or []
            if not isinstance(properties, list):
                properties = []
            print(f"  page {page}: {len(properties)} properties")
            for prop in properties:
                if not isinstance(prop, dict):
                    continue
                card = _card_from_property(prop, max_rent=max_rent)
                if card is None or card.listing_id in seen_ids:
                    continue
                seen_ids.add(card.listing_id)
                page_cards += 1
                _save_cards([card], counts)
            pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
            if not properties:
                break
            # `otherPages` empty means this is the only page. Asking for page 2
            # anyway returns an unrelated, unfiltered batch that is all noise.
            if not pagination.get("nextPage") and not (pagination.get("otherPages") or {}):
                break
        print(f"  kept {page_cards} listing(s) for {name}")
    return counts


def scrape_zillow_search(page, search_name: str, url: str) -> list[ZillowCard]:
    print(f"Polling Zillow search: {search_name}...")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    title = page.title()
    print(f"Page title: {title}")

    if "denied" in title.lower() or "human" in title.lower() or "robot" in title.lower() or "security" in title.lower():
        if not is_interactive():
            print("[zillow] Security block detected in background/automated run. Skipping Zillow to prevent hang.")
            return []

        print("\n" + "=" * 70)
        print(" [ACTION REQUIRED] Zillow's security screen has been triggered!")
        print(" Please click and hold on the verification button in the browser window.")
        print(" Once the rental listings are loaded successfully on your screen,")
        print(" press [ENTER] in this terminal to resume crawling...")
        print("=" * 70 + "\n")
        try:
            input("Press [ENTER] when ready...")
        except (KeyboardInterrupt, EOFError):
            print("\nVerification cancelled.")
            return []

    for _ in range(5):
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(1000)

    cards: list[ZillowCard] = []
    card_locators = page.locator('article[data-test="property-card"], div[data-test="property-card"]')
    count = card_locators.count()

    if count == 0:
        card_locators = page.locator('a.property-card-link')
        count = card_locators.count()

    if count == 0:
        card_locators = page.locator('.search-list li, ul li, [class*="search-list"] li')
        count = card_locators.count()

    print(f"Found {count} potential listing elements on Zillow search page.")

    for i in range(count):
        try:
            card_loc = card_locators.nth(i)
            try:
                parent = card_loc.locator(
                    'xpath=ancestor::article[1]|ancestor::li[1]|ancestor::div[@data-test="property-card"][1]'
                )
                if parent.count():
                    card_loc = parent.first
            except Exception:
                pass

            anchor_loc = card_loc.locator('a[href*="/homedetails/"]').first
            if not anchor_loc.count():
                try:
                    is_anchor = card_loc.evaluate("el => el.tagName.toLowerCase() == 'a'")
                except Exception:
                    is_anchor = False
                anchor_loc = card_loc if is_anchor else card_loc.locator('a[href*="zillow.com"], a[href^="/"]').first

            href = anchor_loc.get_attribute("href") or ""
            if not href:
                continue

            if href.startswith("/"):
                href = f"https://www.zillow.com{href}"
            if "/apartments/" in href and "/homedetails/" not in href:
                continue
            if "/homedetails/" not in href:
                continue

            card_text = ""
            try:
                card_text = " ".join((card_loc.inner_text() or "").split())
            except Exception:
                card_text = ""

            price_text = ""
            price_loc = card_loc.locator('span[data-test="property-card-price"], [class*="price"]').first
            if price_loc.count():
                price_text = price_loc.inner_text()
            if not price_text and card_text:
                price_match = re.search(r"(?:from\s+)?\$\s*[\d,]+", card_text, re.IGNORECASE)
                if price_match:
                    price_text = price_match.group(0)

            if _price_is_vague(price_text):
                continue
            price = _parse_price(price_text)

            address = ""
            addr_loc = card_loc.locator('address[data-test="property-card-addr"]').first
            if addr_loc.count():
                address = addr_loc.inner_text()
            else:
                for selector in ('address', '[class*="Address"]', '[class*="address"]'):
                    candidate = card_loc.locator(selector).first
                    if candidate.count():
                        address = candidate.inner_text()
                        break

            if not address:
                address = "San Francisco, CA"

            clean_address = " ".join(address.split())
            layout = detect_layout(card_text)
            beds = layout.get("beds")
            baths = layout.get("baths")
            layout_bit = f"{beds} bd {baths} ba" if beds is not None else ""
            title = f"Zillow: {clean_address}"
            if layout_bit:
                title = f"Zillow: {layout_bit} — {clean_address}"

            if price is None or _has_synthetic_unit(clean_address):
                continue

            listing_id = _extract_id_from_url(href)
            description = card_text or f"{title}\n{clean_address}"

            cards.append(ZillowCard(
                url=href,
                title=title,
                price=price,
                neighborhood="San Francisco",
                listing_id=listing_id,
                description=description,
                rental_address=clean_address,
                beds=beds,
                baths=baths,
            ))
        except Exception:
            continue

    return cards


def run_poll_cycle_playwright() -> dict[str, int]:
    from playwright.sync_api import sync_playwright

    init_db()
    counts = {"new": 0, "updated": 0, "unchanged": 0}

    headless_mode = not is_interactive()
    if headless_mode:
        print("[zillow] Playwright fallback: headless, skips if blocked.")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless_mode,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.add_init_script(
            "const newProto = navigator.__proto__;"
            "delete newProto.webdriver;"
            "navigator.__proto__ = newProto;"
        )

        for name, url in ZILLOW_SEARCHES:
            try:
                cards = scrape_zillow_search(page, name, url)
                if not cards:
                    page.wait_for_timeout(2000)
                    cards = scrape_zillow_search(page, name, url)
                print(f"Scraped {len(cards)} listings for {name}.")
                _save_cards(cards, counts)
            except Exception as e:
                print(f"Error polling search {name}: {e}", file=sys.stderr)

        browser.close()
    return counts


def run_poll_cycle() -> dict[str, int]:
    use_playwright = os.getenv("ZILLOW_USE_PLAYWRIGHT", "").strip().lower() in ("1", "true", "yes")
    if use_playwright:
        return run_poll_cycle_playwright()
    if _api_key():
        return run_poll_cycle_api()
    print(
        "[zillow] Browser scraping is blocked by Zillow. "
        "Using HasData instead: add HASDATA_API_KEY to .env "
        "(pip package zillow-api-s / https://github.com/HasData/zillow-api-python)."
    )
    return {"new": 0, "updated": 0, "unchanged": 0}


def main() -> int:
    counts = run_poll_cycle()
    print("\nZillow scraping cycle complete:")
    print(
        f"  {counts.get('new', 0)} new, "
        f"{counts.get('updated', 0)} updated, "
        f"{counts.get('unchanged', 0)} unchanged."
    )
    if counts.get("errors"):
        print(f"  {counts['errors']} search error(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
