#!/usr/bin/env python3
"""Zillow scouter using Playwright."""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass

from playwright.sync_api import sync_playwright

from config import ZILLOW_SEARCHES
from db import init_db, upsert_listing

PRICE_RE = re.compile(r"\$\s*([\d,]+)")
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

def _parse_price(text: str) -> int | None:
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None

def _extract_id_from_url(url: str) -> str:
    match = re.search(r"homedetails/([A-Za-z0-9_-]+)_zpid", url)
    if match:
        return f"z-{match.group(1)}"
    h = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
    return f"z-{h}"

def scrape_zillow_search(page, search_name: str, url: str) -> list[ZillowCard]:
    print(f"Polling Zillow search: {search_name}...")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    title = page.title()
    print(f"Page title: {title}")
    
    if "denied" in title.lower() or "human" in title.lower() or "robot" in title.lower() or "security" in title.lower():
        print("\n" + "="*70)
        print(" [ACTION REQUIRED] Zillow's security screen has been triggered!")
        print(" Please click and hold on the verification button in the browser window.")
        print(" Once the rental listings are loaded successfully on your screen,")
        print(" press [ENTER] in this terminal to resume crawling...")
        print("="*70 + "\n")
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

    print(f"Found {count} potential listing elements on Zillow search page.")
    
    for i in range(count):
        try:
            card_loc = card_locators.nth(i)
            anchor_loc = card_loc.locator('a[href*="/homedetails/"]').first
            if not anchor_loc.count():
                anchor_loc = card_loc if "a" in card_loc.evaluate("el => el.tagName.toLowerCase()") else card_loc.locator('a').first
            
            href = anchor_loc.get_attribute("href") or ""
            if not href:
                continue
                
            if href.startswith("/"):
                href = f"https://www.zillow.com{href}"
                
            price_text = ""
            price_loc = card_loc.locator('span[data-test="property-card-price"], [class*="price"]').first
            if price_loc.count():
                price_text = price_loc.inner_text()
            else:
                card_text = card_loc.inner_text() or ""
                price_match = re.search(r"\$[\d,]+", card_text)
                if price_match:
                    price_text = price_match.group(0)
            
            price = _parse_price(price_text)
            
            address = ""
            addr_loc = card_loc.locator('address[data-test="property-card-addr"]').first
            if addr_loc.count():
                address = addr_loc.inner_text()
            else:
                for selector in ('address', '[class*="Address"]'):
                    candidate = card_loc.locator(selector).first
                    if candidate.count():
                        address = candidate.inner_text()
                        break
            
            if not address:
                address = "San Francisco, CA"
                
            clean_address = " ".join(address.split())
            title = f"Zillow Rental: {clean_address}"
            
            parts = [p.strip() for p in clean_address.split(",")]
            neighborhood = parts[0] if parts else "SF"
            listing_id = _extract_id_from_url(href)
            
            cards.append(ZillowCard(
                url=href,
                title=title,
                price=price,
                neighborhood=neighborhood,
                listing_id=listing_id
            ))
        except Exception:
            continue
            
    return cards

def run_poll_cycle() -> dict[str, int]:
    init_db()
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800}
        )
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
                
                for card in cards:
                    try:
                        result = upsert_listing(
                            listing_id=card.listing_id,
                            url=card.url,
                            title=card.title,
                            price=card.price,
                            neighborhood=card.neighborhood,
                            source="zillow"
                        )
                        counts[result] = counts.get(result, 0) + 1
                    except Exception as e:
                        print(f"Error saving Zillow card {card.listing_id}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error polling search {name}: {e}", file=sys.stderr)
                
        browser.close()
        
    return counts

def main() -> int:
    counts = run_poll_cycle()
    print("\nZillow scraping cycle complete:")
    print(f"  {counts.get('new', 0)} new, {counts.get('updated', 0)} updated, {counts.get('unchanged', 0)} unchanged.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
