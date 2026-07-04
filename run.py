#!/usr/bin/env python3
"""Orchestrator: scout → filter → rank → outreach.

Interactive Telegram bot (commands /top, /tram, /run, etc.):

    python bot.py

Open https://t.me/Rae_house_bot and tap Start once to register your chat_id.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from config import POLL_INTERVAL_HOURS, SEARCH_CRITERIA
from db import get_matching_listings, init_pipeline_tables

# Import pipeline stages (avoid naming conflict with stdlib 'filter')
import scout
import filter as listing_filter
import rank
import outreach
import notify


STAGES = ("scout", "facebook", "filter", "rank", "outreach")


def run_pipeline(stages: tuple[str, ...] = STAGES) -> dict[str, int]:
    """Run selected pipeline stages in order. Returns per-stage counts."""
    init_pipeline_tables()
    results: dict[str, int] = {}

    if "scout" in stages:
        print("▶ Scout: fetching Craigslist listings…")
        counts = scout.run_poll_cycle()
        results["scout"] = counts.get("new", 0)
        print(
            f"  → {results['scout']} new, "
            f"{counts.get('updated', 0)} updated, "
            f"{counts.get('unchanged', 0)} unchanged"
        )

    if "facebook" in stages:
        print("▶ Facebook: polling Marketplace…")
        try:
            import scout_facebook
            from facebook_session import session_configured

            if not session_configured():
                print("  → skipped (run: python scout_facebook.py login)")
                results["facebook"] = 0
            else:
                fb_counts = scout_facebook.run_poll_cycle()
                results["facebook"] = fb_counts.get("new", 0)
                print(
                    f"  → {results['facebook']} new, "
                    f"{fb_counts.get('updated', 0)} updated"
                )
        except Exception as exc:
            print(f"  warning: Facebook scout failed: {exc}", file=sys.stderr)
            results["facebook"] = 0

    if "filter" in stages:
        print("▶ Tag: move-in + room-type tags (filter.py)…")
        results["filter"] = listing_filter.run()
        print(f"  → {results['filter']} listing(s) tagged")

    if "rank" in stages:
        print("▶ Rank: writing digest.md…")
        results["rank"] = rank.run()
        print(f"  → {results['rank']} listing(s) in digest")

    if "outreach" in stages:
        print("▶ Outreach: drafting messages…")
        results["outreach"] = outreach.run()
        print(f"  → {results['outreach']} draft(s) created")

    return results


def print_top_listings(n: int = 5) -> None:
    top = get_matching_listings(limit=n, exclude_scams=True)
    if not top:
        print("\nNo matches yet. Run scout + filter stages first.")
        return

    print(f"\n{'=' * 60}")
    print(f"MATCHES ({min(n, len(top))}) — Aug 1–18, ≤$1300")
    print(f"{'=' * 60}")
    for i, listing in enumerate(top, 1):
        price = listing.get("price")
        price_str = f"${price}" if price else "price n/a"
        reasoning = (listing.get("reasoning") or "")[:80]
        source_tag = " 📘" if (listing.get("source") or "") == "facebook" else ""
        print(f"\n{i}. {listing.get('title', 'Untitled')}{source_tag}")
        print(f"   {price_str} · {listing.get('neighborhood', 'SF')}")
        if reasoning:
            print(f"   {reasoning}")
        print(f"   {listing.get('url', '')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SF room-finding pipeline: scout → filter → rank → outreach"
    )
    parser.add_argument(
        "--scout-only", action="store_true", help="Run scout stage only"
    )
    parser.add_argument(
        "--facebook-only", action="store_true", help="Run Facebook Marketplace scout only"
    )
    parser.add_argument(
        "--with-facebook",
        action="store_true",
        help="Include Facebook Marketplace after Craigslist scout",
    )
    parser.add_argument(
        "--filter-only", action="store_true", help="Run filter stage only"
    )
    parser.add_argument(
        "--rank-only", action="store_true", help="Run rank stage only"
    )
    parser.add_argument(
        "--outreach-only", action="store_true", help="Run outreach stage only"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top listings to display (default: 5)",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="After rank stage, alert on top 5 new listings scoring >= 80",
    )
    parser.add_argument(
        "--alert-channel",
        choices=("telegram", "slack"),
        default="telegram",
        help="Notification channel when --alert is set (default: telegram)",
    )
    return parser.parse_args(argv)


def _resolve_stages(args: argparse.Namespace) -> tuple[str, ...]:
    only_flags = {
        "scout": args.scout_only,
        "facebook": args.facebook_only,
        "filter": args.filter_only,
        "rank": args.rank_only,
        "outreach": args.outreach_only,
    }
    selected = [s for s, flag in only_flags.items() if flag]
    if selected:
        return tuple(selected)
    return STAGES


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stages = _resolve_stages(args)

    print(f"SF Room Finder — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(
        f"Criteria: private room, ≤${SEARCH_CRITERIA['max_rent']}, "
        f"move-in {SEARCH_CRITERIA['move_in_start']}–{SEARCH_CRITERIA['move_in_end']}"
    )
    print(f"Poll interval: every {POLL_INTERVAL_HOURS}h")
    print(f"Stages: {' → '.join(stages)}\n")

    run_pipeline(stages)

    if args.alert:
        if "rank" not in stages:
            print("⚠ --alert requires the rank stage (run full pipeline or --rank-only).")
        else:
            print("▶ Alert: checking for new high-score listings…")
            candidates = get_ranked_listings(limit=50, exclude_scams=True)
            result = notify.send_digest_alert(
                candidates,
                channel=args.alert_channel,
                min_score=notify.MIN_SCORE_FOR_ALERT,
                limit=notify.TOP_N_ALERT,
            )
            if result == "sent":
                print("  → Alert sent")
            elif result == "dry_run":
                print("  → Dry-run preview printed (set tokens in .env to send)")
            else:
                print("  → No new listings scoring >= 80 to alert")

    print_top_listings(args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())