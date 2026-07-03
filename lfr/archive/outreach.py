#!/usr/bin/env python3
"""Draft friendly inquiry messages for top 3 unapplied listings."""

from __future__ import annotations

import sys
from pathlib import Path

from apply import create_application, load_profile
from db import _is_short_term_listing, get_unapplied_ranked_listings, init_db

OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / "outreach_drafts.txt"
TOP_N = 3


def run() -> int:
    """Write outreach drafts for top unapplied listings. Returns draft count."""
    init_db()
    profile = load_profile()
    rows = get_unapplied_ranked_listings(
        limit=TOP_N,
        exclude_scams=True,
        exclude_short_term=True,
    )
    if not rows:
        print("No unapplied ranked monthly listings. Run filter.py first.")
        return 0

    sections: list[str] = []
    drafted = 0
    for listing in rows:
        if _is_short_term_listing(listing.get("flags_json")):
            continue
        drafted += 1
        # create_application → build_draft uses profile.message_template when set
        result = create_application(listing["id"], profile)
        message = result["draft_text"]
        block = (
            f"{'=' * 60}\n"
            f"DRAFT {drafted}: {listing.get('title', 'Untitled')}\n"
            f"Score: {listing.get('score')} | ${listing.get('price')} | "
            f"{listing.get('neighborhood')}\n"
            f"URL: {listing.get('url')}\n"
            f"{'-' * 60}\n"
            f"{message}\n"
        )
        sections.append(block)
        print(block)

    OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {drafted} draft(s) to {OUTPUT_PATH}")
    return drafted


def main() -> int:
    try:
        count = run()
        return 0 if count else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())