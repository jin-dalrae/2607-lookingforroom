#!/usr/bin/env python3
"""Database clean-up utility: check active listing URLs and prune expired ones."""

from __future__ import annotations

import concurrent.futures
import re
import sys
import requests

from db import get_connection, init_db
from lfr.db.applications import mark_application_rejected

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DELETED_PATTERNS = [
    re.compile(r"this posting has been deleted", re.IGNORECASE),
    re.compile(r"this posting has expired", re.IGNORECASE),
    re.compile(r"posting deleted", re.IGNORECASE),
    re.compile(r"flagged for removal", re.IGNORECASE),
    re.compile(r"this content isn't available", re.IGNORECASE),
    re.compile(r"listing is no longer available", re.IGNORECASE),
    re.compile(r"this home is off market", re.IGNORECASE),
    re.compile(r"no longer available", re.IGNORECASE),
]

def is_url_dead(url: str, source: str) -> bool:
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        res = session.get(url, timeout=10, allow_redirects=True)
        
        if res.status_code == 404:
            return True
            
        if source == "facebook" and "marketplace/item" not in res.url:
            return True
            
        text = res.text
        for pattern in DELETED_PATTERNS:
            if pattern.search(text):
                return True
                
        return False
    except Exception as e:
        return False

def check_listing(row: dict) -> tuple[str, bool]:
    listing_id = row["id"]
    url = row["url"]
    source = row.get("source", "craigslist")
    dead = is_url_dead(url, source)
    return listing_id, dead

def main() -> int:
    init_db()
    
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.id, l.url, l.source FROM listings l
            LEFT JOIN applications a ON a.listing_id = l.id
            WHERE a.status IS NULL OR a.status != 'rejected'
            """
        ).fetchall()
        
    listings = [dict(row) for row in rows]
    print(f"Found {len(listings)} active listing(s) to verify...")
    
    if not listings:
        print("No active listings to check.")
        return 0
        
    pruned_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_listing = {
            executor.submit(check_listing, listing): listing
            for listing in listings
        }
        
        for future in concurrent.futures.as_completed(future_to_listing):
            listing = future_to_listing[future]
            try:
                listing_id, dead = future.result()
                if dead:
                    print(f"❌ DEAD URL DETECTED: {listing['url']} (Marking deleted)")
                    mark_application_rejected(listing_id)
                    pruned_count += 1
            except Exception as e:
                print(f"Error processing {listing['url']}: {e}", file=sys.stderr)
                
    print(f"\nCompleted checking {len(listings)} active listings.")
    print(f"  → Pruned {pruned_count} dead listing(s).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
