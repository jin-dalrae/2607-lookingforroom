#!/usr/bin/env python3
"""Poll Craigslist SF + Oakland rooms under $1300 and store listings in SQLite."""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from lfr.config import (
    AUGUST_ROOM_CRAIGSLIST_URL,
    CASTRO_CRAIGSLIST_URL,
    CHINATOWN_CRAIGSLIST_URL,
    CIVIC_CRAIGSLIST_URL,
    CRAIGSLIST_URL,
    DOGPATCH_CRAIGSLIST_URL,
    DOWNTOWN_SF_CRAIGSLIST_URL,
    EMBARCADERO_CRAIGSLIST_URL,
    FINANCIAL_CRAIGSLIST_URL,
    HAYES_CRAIGSLIST_URL,
    INNER_MISSION_CRAIGSLIST_URL,
    MARINA_CRAIGSLIST_URL,
    MISSION_BAY_CRAIGSLIST_URL,
    MISSION_CRAIGSLIST_URL,
    NOE_VALLEY_CRAIGSLIST_URL,
    NORTH_BEACH_CRAIGSLIST_URL,
    POTRERO_CRAIGSLIST_URL,
    RUSSIAN_HILL_CRAIGSLIST_URL,
    SOUTH_BEACH_CRAIGSLIST_URL,
    SOMA_CRAIGSLIST_URL,
    VAN_NESS_CRAIGSLIST_URL,
)
from lfr.db import init_db, upsert_listing
from lfr.db.listings import (
    listing_already_known,
    listing_id_candidates_from_url,
    should_skip_detail_scrape,
)

# Dedicated neighborhood queries (constants may also exist for unused/legacy areas)
BERNAL_CRAIGSLIST_URL = f"{CRAIGSLIST_URL}&query=bernal+heights+room"
PANHANDLE_CRAIGSLIST_URL = f"{CRAIGSLIST_URL}&query=panhandle+room"

SEARCH_URLS = [
    ("San Francisco", CRAIGSLIST_URL),
    ("Dogpatch", DOGPATCH_CRAIGSLIST_URL),
    ("Noe Valley", NOE_VALLEY_CRAIGSLIST_URL),
    ("Mission District", MISSION_CRAIGSLIST_URL),
    ("Inner Mission", INNER_MISSION_CRAIGSLIST_URL),
    ("Hayes Valley", HAYES_CRAIGSLIST_URL),
    ("Castro", CASTRO_CRAIGSLIST_URL),
    ("Bernal Heights", BERNAL_CRAIGSLIST_URL),
    ("Panhandle", PANHANDLE_CRAIGSLIST_URL),
    ("Marina", MARINA_CRAIGSLIST_URL),
    ("Chinatown", CHINATOWN_CRAIGSLIST_URL),
    ("North Beach", NORTH_BEACH_CRAIGSLIST_URL),
    ("Russian Hill", RUSSIAN_HILL_CRAIGSLIST_URL),
    ("Downtown SF", DOWNTOWN_SF_CRAIGSLIST_URL),
    ("SOMA", SOMA_CRAIGSLIST_URL),
    ("South Beach", SOUTH_BEACH_CRAIGSLIST_URL),
    ("Mission Bay", MISSION_BAY_CRAIGSLIST_URL),
    ("Potrero Hill", POTRERO_CRAIGSLIST_URL),
    ("Civic Center", CIVIC_CRAIGSLIST_URL),
    ("Financial District", FINANCIAL_CRAIGSLIST_URL),
    ("Embarcadero", EMBARCADERO_CRAIGSLIST_URL),
    ("Van Ness", VAN_NESS_CRAIGSLIST_URL),
    ("August available", AUGUST_ROOM_CRAIGSLIST_URL),
]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
DETAIL_DELAY_SEC = 1.0


@dataclass
class ListingCard:
    url: str
    title: str
    price: int | None
    neighborhood: str
    post_id: str
    source_area: str


class ScoutError(Exception):
    """Raised when scraping fails."""


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _parse_price(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else None


def _listing_id_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if path else url
    return slug or url


def fetch_search_results(
    session: requests.Session,
    search_url: str,
    source_area: str,
) -> list[ListingCard]:
    """Parse listing cards from a Craigslist search page."""
    try:
        response = session.get(search_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScoutError(f"Failed to fetch search page ({source_area}): {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    cards: list[ListingCard] = []

    for item in soup.select("li.cl-static-search-result"):
        link = item.select_one("a[href]")
        if not link:
            continue

        url = link.get("href", "").strip()
        if not url:
            continue

        title_el = item.select_one(".title")
        price_el = item.select_one(".price")
        location_el = item.select_one(".location")

        title = (title_el.get_text(strip=True) if title_el else item.get("title", "")).strip()
        neighborhood = location_el.get_text(strip=True) if location_el else ""
        price = _parse_price(price_el.get_text(strip=True) if price_el else None)

        cards.append(
            ListingCard(
                url=url,
                title=title,
                price=price,
                neighborhood=neighborhood,
                post_id=_listing_id_from_url(url),
                source_area=source_area,
            )
        )

    return cards


def fetch_listing_details(
    session: requests.Session, url: str
) -> tuple[str, str, str | None, bool]:
    """
    Fetch an individual listing page.

    Returns (post_id, description, posted_at_iso, is_unavailable).
    """
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  warning: failed to fetch {url}: {exc}", file=sys.stderr)
        return _listing_id_from_url(url), "", None, False

    try:
        from lfr.check_urls import page_indicates_unavailable

        if page_indicates_unavailable(
            status_code=response.status_code,
            text=response.text or "",
            url=response.url or url,
            source="craigslist",
        ):
            return _listing_id_from_url(url), "", None, True
    except Exception:
        pass

    if response.status_code >= 400:
        print(
            f"  warning: failed to fetch {url}: HTTP {response.status_code}",
            file=sys.stderr,
        )
        return _listing_id_from_url(url), "", None, False

    soup = BeautifulSoup(response.text, "html.parser")

    from lfr.listings.dates import parse_posted_at

    post_id = _listing_id_from_url(url)
    posted_at: str | None = None
    posting_blob = ""
    for info in soup.select("p.postinginfo"):
        text = info.get_text(" ", strip=True)
        posting_blob = f"{posting_blob} {text}".strip()
        match = re.search(r"post id:\s*(\d+)", text, re.IGNORECASE)
        if match:
            post_id = match.group(1)
            break
    time_el = soup.select_one("time.date.timeago")
    if time_el and time_el.get("datetime"):
        from lfr.listings.dates import normalize_iso_timestamp

        posting_blob = f"{posting_blob} {time_el['datetime']}".strip()
        posted_at = normalize_iso_timestamp(time_el["datetime"])
    if not posted_at:
        posted_at = parse_posted_at(posting_blob)

    body = soup.select_one("section#postingbody")
    if body:
        for removable in body.select(".print-information"):
            removable.decompose()
        description = body.get_text("\n", strip=True)
    else:
        description = ""

    if posting_blob:
        description = f"{posting_blob}\n\n{description}" if description else posting_blob

    return post_id, description, posted_at, False


def _collect_cards(session: requests.Session) -> list[ListingCard]:
    """Fetch cards from all configured search URLs, deduped by URL."""
    seen_urls: set[str] = set()
    all_cards: list[ListingCard] = []

    for area_name, search_url in SEARCH_URLS:
        print(f"Fetching search results: {area_name}")
        try:
            cards = fetch_search_results(session, search_url, area_name)
        except ScoutError as exc:
            print(f"  warning: {exc}", file=sys.stderr)
            continue

        print(f"  → {len(cards)} listing(s) on search page")
        for card in cards:
            if card.url in seen_urls:
                continue
            seen_urls.add(card.url)
            all_cards.append(card)

    return all_cards


def run_poll_cycle() -> dict[str, int]:
    """Run one poll cycle across SF + Oakland and return counts by outcome."""
    init_db()
    session = _session()

    cards = _collect_cards(session)
    if not cards:
        print("warning: no listings found on any search page", file=sys.stderr)

    counts = {"new": 0, "updated": 0, "unchanged": 0, "errors": 0}

    for index, card in enumerate(cards, start=1):
        try:
            id_guesses = listing_id_candidates_from_url(card.url)
            existing = listing_already_known(
                url=card.url,
                listing_id=card.post_id or (id_guesses[0] if id_guesses else None),
            )
            # Already in DB / apply list with content — touch last_seen only, no detail HTTP
            if should_skip_detail_scrape(existing):
                outcome = upsert_listing(
                    listing_id=str(existing["id"]),
                    url=card.url,
                    title=card.title,
                    price=card.price,
                    neighborhood=card.neighborhood or None,
                    description=None,
                    posted_at=None,
                    source="craigslist",
                )
                counts[outcome] += 1
                counts["skipped_detail"] = counts.get("skipped_detail", 0) + 1
                continue

            if index > 1:
                time.sleep(DETAIL_DELAY_SEC)
            post_id, description, posted_at, unavailable = fetch_listing_details(
                session, card.url
            )
            listing_id = post_id or card.post_id
            if unavailable:
                try:
                    from lfr.check_urls import mark_dead_listing

                    mark_dead_listing(listing_id)
                    counts["unavailable"] = counts.get("unavailable", 0) + 1
                    print(f"  dead listing removed: {card.url}")
                except Exception as exc:
                    print(
                        f"  warning: could not mark dead {card.url}: {exc}",
                        file=sys.stderr,
                    )
                continue

            outcome = upsert_listing(
                listing_id=listing_id,
                url=card.url,
                title=card.title,
                price=card.price,
                neighborhood=card.neighborhood,
                description=description,
                posted_at=posted_at,
                source="craigslist",
            )
            counts[outcome] += 1
        except Exception as exc:
            counts["errors"] += 1
            print(f"  warning: failed to store {card.url}: {exc}", file=sys.stderr)

    return counts


def main() -> int:
    print("Polling Craigslist:")
    for area_name, search_url in SEARCH_URLS:
        print(f"  {area_name}: {search_url}")
    counts = run_poll_cycle()

    total = counts["new"] + counts["updated"] + counts["unchanged"]
    skipped = counts.get("skipped_detail", 0)
    print(
        f"Done. {total} listings processed: "
        f"{counts['new']} new, {counts['updated']} updated, "
        f"{counts['unchanged']} unchanged"
        + (f", {skipped} already known (no detail re-fetch)" if skipped else "")
    )
    if counts["errors"]:
        print(f"Errors: {counts['errors']}", file=sys.stderr)

    return 1 if counts["errors"] and total == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())