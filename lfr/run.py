#!/usr/bin/env python3
"""Orchestrator: scout → filter → rank → export helpers.

Usage:
    python run.py
    python run.py --scout-only
    python run.py --with-facebook
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from lfr.config import POLL_INTERVAL_HOURS, SEARCH_CRITERIA
from lfr.db import get_matching_listings, init_pipeline_tables
from lfr.users import current_user

# Import pipeline stages (avoid naming conflict with stdlib 'filter')
import lfr.scout.craigslist as scout
import lfr.score as listing_filter
import lfr.rank as rank
import lfr.archive.outreach as outreach


STAGES = ("scout", "facebook", "zillow", "filter", "prune", "rank", "outreach")


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
            import lfr.scout.facebook as scout_facebook
            from lfr.scout.session import session_configured

            if not session_configured():
                print("  → skipped (run: python -m lfr.scout.facebook login)")
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

    if "zillow" in stages:
        print("▶ Zillow: polling rentals…")
        try:
            import lfr.scout.zillow as scout_zillow

            zillow_counts = scout_zillow.run_poll_cycle()
            results["zillow"] = zillow_counts.get("new", 0)
            print(
                f"  → {results['zillow']} new, "
                f"{zillow_counts.get('updated', 0)} updated"
            )
        except Exception as exc:
            print(f"  warning: Zillow scout failed: {exc}", file=sys.stderr)
            results["zillow"] = 0

    if "filter" in stages:
        print("▶ Score: tag + rank listings (local heuristics by default)…")
        results["filter"] = listing_filter.run()
        print(f"  → {results['filter']} listing(s) scored")

    # Auto-delete to-apply / applied rows whose public post is gone.
    should_prune = "prune" in stages or (
        "prune" not in stages
        and any(s in stages for s in ("scout", "facebook", "zillow", "filter"))
    )
    if should_prune:
        print("▶ Prune: delete to-apply / applied listings with unavailable posts…")
        try:
            import os

            from lfr.check_urls import prune_unavailable_listings

            raw_limit = os.getenv("PRUNE_URL_LIMIT", "200").strip()
            limit = int(raw_limit) if raw_limit.isdigit() and int(raw_limit) > 0 else 200
            workers_raw = os.getenv("PRUNE_URL_WORKERS", "3").strip()
            workers = int(workers_raw) if workers_raw.isdigit() else 3
            prune_result = prune_unavailable_listings(
                max_workers=max(1, workers),
                limit=limit,
            )
            results["prune"] = prune_result.get("pruned", 0)
            print(
                f"  → checked {prune_result.get('checked', 0)}, "
                f"deleted {results['prune']} unavailable"
            )
        except Exception as exc:
            print(f"  warning: URL prune failed: {exc}", file=sys.stderr)
            results["prune"] = 0

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
    print(f"MATCHES ({min(n, len(top))})")
    print(f"{'=' * 60}")
    for i, listing in enumerate(top, 1):
        price = listing.get("price")
        price_str = f"${price}" if price else "price n/a"
        reasoning = (listing.get("reasoning") or "")[:80]
        src = (listing.get("source") or "").lower()
        source_tag = " 📘" if src == "facebook" else (" 💚" if src == "zillow" else "")
        print(f"\n{i}. {listing.get('title', 'Untitled')}{source_tag}")
        print(f"   {price_str} · {listing.get('neighborhood', 'SF')}")
        if reasoning:
            print(f"   {reasoning}")
        print(f"   {listing.get('url', '')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Room-finding pipeline: scout → score → rank"
    )
    parser.add_argument(
        "--scout-only", action="store_true", help="Run scout stage only"
    )
    parser.add_argument(
        "--facebook-only", action="store_true", help="Run Facebook Marketplace scout only"
    )
    parser.add_argument(
        "--zillow-only", action="store_true", help="Run Zillow rentals scout only"
    )
    parser.add_argument(
        "--with-facebook",
        action="store_true",
        help="Include Facebook Marketplace after Craigslist scout",
    )
    parser.add_argument(
        "--with-zillow",
        action="store_true",
        help="Include Zillow rentals after Craigslist scout",
    )
    parser.add_argument(
        "--filter-only", action="store_true", help="Run scoring stage only"
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
    return parser.parse_args(argv)


def _resolve_stages(args: argparse.Namespace) -> tuple[str, ...]:
    only_flags = {
        "scout": args.scout_only,
        "facebook": args.facebook_only,
        "zillow": args.zillow_only,
        "filter": args.filter_only,
        "rank": args.rank_only,
        "outreach": args.outreach_only,
    }
    selected = [s for s, flag in only_flags.items() if flag]
    if selected:
        return tuple(selected)

    if args.with_facebook or args.with_zillow:
        stages = ["scout"]
        if args.with_facebook:
            stages.append("facebook")
        if args.with_zillow:
            stages.append("zillow")
        stages.extend(["filter", "rank", "outreach"])
        return tuple(stages)

    return STAGES


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stages = _resolve_stages(args)

    print(f"Looking for Room — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(
        f"User: {current_user().name} · "
        f"≤${SEARCH_CRITERIA['max_rent']}"
        + (
            f", move-in {SEARCH_CRITERIA['move_in_start']}–{SEARCH_CRITERIA['move_in_end']}"
            if SEARCH_CRITERIA.get("require_move_in_window")
            else ", move-in flexible"
        )
    )
    print(f"Poll interval: every {POLL_INTERVAL_HOURS}h")
    print(f"Stages: {' → '.join(stages)}\n")

    run_pipeline(stages)
    print_top_listings(args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
