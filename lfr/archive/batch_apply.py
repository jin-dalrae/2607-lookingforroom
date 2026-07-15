#!/usr/bin/env python3
"""Batch-create application drafts and open them in a local HTML helper page."""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import Any

from lfr.apply import create_application, load_profile
from lfr.db import _is_short_term_listing, get_unapplied_ranked_listings, init_db

OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / "batch_apply.html"
DEFAULT_TOP = 5


def _listing_card(index: int, listing: dict[str, Any], message: str) -> str:
    title = html.escape(listing.get("title") or "Untitled")
    price = listing.get("price")
    price_label = html.escape(f"${price}/mo" if price else "N/A")
    url = html.escape(listing.get("url") or "")
    score = listing.get("score")
    score_bit = f" · score {score}" if score is not None else ""
    neighborhood = html.escape(listing.get("neighborhood") or "Unknown")
    message_html = html.escape(message)

    return f"""
    <section class="listing">
      <header>
        <h2>{index}. {title}</h2>
        <p class="meta">{price_label} · {neighborhood}{score_bit}</p>
      </header>
      <textarea rows="14" readonly>{message_html}</textarea>
      <div class="actions">
        <a class="button" href="{url}" target="_blank" rel="noopener noreferrer">Open listing</a>
      </div>
    </section>
    """


def build_html(drafts: list[tuple[dict[str, Any], str]], *, top_n: int) -> str:
    cards = "\n".join(
        _listing_card(i, listing, message)
        for i, (listing, message) in enumerate(drafts, 1)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Batch apply — {len(drafts)} listing(s)</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1.5rem;
      background: #f5f5f7;
      color: #1d1d1f;
    }}
    h1 {{ margin-top: 0; }}
    .listing {{
      background: #fff;
      border-radius: 12px;
      padding: 1rem 1.25rem 1.25rem;
      margin-bottom: 1rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    }}
    .listing h2 {{
      margin: 0 0 0.35rem;
      font-size: 1.1rem;
    }}
    .meta {{
      margin: 0 0 0.75rem;
      color: #6e6e73;
      font-size: 0.95rem;
    }}
    textarea {{
      width: 100%;
      box-sizing: border-box;
      font: inherit;
      line-height: 1.45;
      padding: 0.75rem;
      border: 1px solid #d2d2d7;
      border-radius: 8px;
      resize: vertical;
      background: #fafafa;
    }}
    .actions {{ margin-top: 0.75rem; }}
    .button {{
      display: inline-block;
      padding: 0.55rem 1rem;
      background: #0071e3;
      color: #fff;
      text-decoration: none;
      border-radius: 8px;
      font-weight: 600;
    }}
    .button:hover {{ background: #0077ed; }}
    .hint {{
      color: #6e6e73;
      font-size: 0.9rem;
    }}
  </style>
</head>
<body>
  <h1>Batch apply</h1>
  <p class="hint">Top {top_n} unapplied listings. Copy each message, open the listing, paste into Craigslist reply.</p>
  <p class="hint"><strong>After you send all messages:</strong> run <code>python sync.py --catch-up</code> or send <code>/sentall</code> in Telegram so applications move from draft → sent.</p>
  {cards}
</body>
</html>
"""


def run(top: int = DEFAULT_TOP) -> tuple[int, Path, list[dict[str, Any]]]:
    """Create drafts for top N unapplied listings and write batch_apply.html."""
    init_db()
    profile = load_profile()
    rows = get_unapplied_ranked_listings(limit=top)
    if not rows:
        OUTPUT_PATH.write_text(
            build_html([], top_n=top),
            encoding="utf-8",
        )
        print("No unapplied ranked listings. Run filter.py /rank first.")
        print(f"Wrote empty page to {OUTPUT_PATH.resolve()}")
        return 0, OUTPUT_PATH.resolve(), []

    drafts: list[tuple[dict[str, Any], str]] = []
    listings_out: list[dict[str, Any]] = []
    for listing in rows:
        if _is_short_term_listing(listing.get("flags_json")):
            continue
        result = create_application(listing["id"], profile)
        message = result["draft_text"]
        drafts.append((listing, message))
        listings_out.append(listing)
        print(
            f"Draft {len(drafts)}: {listing.get('title', 'Untitled')} "
            f"[{listing.get('score')}] ${listing.get('price')}"
        )

    OUTPUT_PATH.write_text(build_html(drafts, top_n=top), encoding="utf-8")
    print(f"\nCreated {len(drafts)} draft(s)")
    print(f"Open: file://{OUTPUT_PATH.resolve()}")
    return len(drafts), OUTPUT_PATH.resolve(), listings_out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batch draft Craigslist applications for top unapplied listings",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        metavar="N",
        help=f"Number of unapplied listings to draft (default: {DEFAULT_TOP})",
    )
    ns = parser.parse_args(argv)

    if ns.top < 1:
        print("--top must be at least 1", file=sys.stderr)
        return 1

    try:
        count, _, _ = run(top=ns.top)
        return 0 if count else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())