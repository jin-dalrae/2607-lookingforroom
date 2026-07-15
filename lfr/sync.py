#!/usr/bin/env python3
"""CLI to sync application tracking after manual Craigslist outreach."""

from __future__ import annotations

import argparse
import sys

from lfr.channels import default_channel_for_listing, normalize_channel, parse_channel_args
from lfr.db import (
    get_application_stats,
    get_listing_by_id,
    get_listing_by_url,
    init_db,
    list_applications,
    mark_all_drafts_sent,
    mark_application_sent,
    mark_applications_sent_bulk,
    mark_ranked_sent,
    update_application_channel,
    update_applications_channel_bulk,
)


def format_status_dashboard() -> str:
    stats = get_application_stats()
    lines = [
        "Application pipeline",
        f"  sent:     {stats.get('sent', 0)}",
        f"  replied:  {stats.get('replied', 0)}",
        f"  toured:   {stats.get('toured', 0)}",
        f"  rejected: {stats.get('rejected', 0)}",
        f"  draft:    {stats.get('draft', 0)}",
        f"  accepted: {stats.get('accepted', 0)}",
        f"  awaiting fresh (unapplied ranked): {stats.get('awaiting_fresh', 0)}",
        f"  total tracked: {stats.get('total', 0)}",
    ]
    return "\n".join(lines)


def print_recent_applications(limit: int = 10) -> None:
    apps = list_applications(limit=limit)
    if not apps:
        print("No applications tracked yet.")
        return
    print(f"\nRecent applications (up to {limit}):")
    for i, app in enumerate(apps, 1):
        title = (app.get("title") or "Untitled")[:50]
        price = f"${app['price']}" if app.get("price") else "N/A"
        sent = app.get("sent_at") or ""
        sent_bit = f" · sent {sent[:10]}" if sent else ""
        ch = app.get("channel") or ""
        ch_bit = f" · {ch}" if ch else ""
        print(
            f"  {i}. [{app['status']}] {title} — {price}{ch_bit}{sent_bit}\n"
            f"     {app.get('url', '')}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync application tracking after you send Craigslist messages",
    )
    parser.add_argument(
        "--catch-up",
        action="store_true",
        help="Mark all draft applications as sent (after batch_apply)",
    )
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Mark top N ranked listings as sent",
    )
    parser.add_argument(
        "--url",
        metavar="URL",
        help="Mark one listing URL as sent",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print application pipeline dashboard",
    )
    parser.add_argument(
        "--channel",
        default=None,
        choices=("craigslist", "email", "imessage", "phone", "facebook", "other"),
        help="Outreach channel (default: auto from listing source)",
    )
    parser.add_argument(
        "--rechannel",
        action="store_true",
        help="Only update channel on an existing application (use with --url or --top)",
    )
    parser.add_argument(
        "--ranks",
        metavar="N,M,...",
        help="Comma-separated rank positions to mark or rechannel (e.g. 1,3,5)",
    )
    ns = parser.parse_args(argv)

    if not any((ns.catch_up, ns.top, ns.url, ns.status, ns.ranks)):
        parser.print_help()
        return 1

    init_db()

    try:
        if ns.catch_up:
            count = mark_all_drafts_sent(channel=ns.channel)
            channel_note = ns.channel or "auto (per listing)"
            print(f"Catch-up: marked {count} draft(s) as sent via {channel_note}.")

        if ns.top is not None:
            if ns.top < 1:
                print("--top must be at least 1", file=sys.stderr)
                return 1
            channel = ns.channel or "craigslist"
            count = mark_ranked_sent(ns.top, channel=channel)
            print(f"Marked top {ns.top} ranked listing(s) as sent ({count} updated).")

        if ns.url:
            listing = get_listing_by_url(ns.url.strip())
            if listing is None:
                path = ns.url.rstrip("/").split("/")[-1]
                listing = get_listing_by_id(path)
            if listing is None:
                print(f"Listing not found: {ns.url}", file=sys.stderr)
                return 1
            channel = ns.channel or default_channel_for_listing(listing)
            if ns.rechannel:
                app = update_application_channel(listing["id"], channel=channel)
                verb = "Rechanneled"
            else:
                app = mark_application_sent(listing["id"], channel=channel)
                verb = "Marked sent"
            title = (listing.get("title") or listing["id"])[:60]
            print(f"{verb}: {title}")
            if app:
                print(f"  status={app['status']} channel={app.get('channel')}")
            elif ns.rechannel:
                print("  No application row for this listing.", file=sys.stderr)
                return 1

        if ns.ranks:
            positions = []
            for part in ns.ranks.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    positions.append(int(part))
                except ValueError:
                    print(f"Invalid rank: {part!r}", file=sys.stderr)
                    return 1
            if not positions:
                print("--ranks requires at least one number", file=sys.stderr)
                return 1
            listing_ids = []
            for pos in positions:
                from lfr.db import get_ranked_listing_at_position

                listing = get_ranked_listing_at_position(pos)
                if listing is None:
                    print(f"Rank #{pos} not found.", file=sys.stderr)
                    return 1
                listing_ids.append(listing["id"])
            channel = ns.channel or "craigslist"
            if ns.rechannel:
                count = update_applications_channel_bulk(listing_ids, channel=channel)
                print(f"Rechanneled {count} listing(s) to {channel}.")
            else:
                count = mark_applications_sent_bulk(listing_ids, channel=channel)
                print(f"Marked {count} listing(s) as sent via {channel}.")

        if ns.status or ns.catch_up or ns.top or ns.url or ns.ranks:
            print()
            print(format_status_dashboard())
            if ns.status:
                print_recent_applications()

        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())