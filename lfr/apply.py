#!/usr/bin/env python3
"""Application engine — draft Craigslist inquiry messages from profile.yaml."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from channels import default_channel_for_listing, is_facebook_listing
from db import (
    _listing_with_score,
    get_first_unapplied_ranked_listing,
    get_listing_by_id,
    get_listing_by_url,
    get_ranked_listing_at_position,
    get_ranked_listings,
    init_db,
    upsert_application_draft,
)
from rank import _move_in_from_flags, _size_from_flags

from lfr.paths import PROJECT_ROOT
PROFILE_PATH = PROJECT_ROOT / "profile.yaml"


UTILITIES_INCLUDED_RE = re.compile(
    r"utilities?\s+(?:included|incl\.?|covered)",
    re.IGNORECASE,
)


def load_profile(path: Path | None = None) -> dict[str, Any]:
    """Load applicant profile from profile.yaml."""
    profile_path = path or PROFILE_PATH
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Profile not found: {profile_path}. "
            "Copy profile.example.yaml to profile.yaml and fill in your details."
        )
    with profile_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile format in {profile_path}")
    return data


def _utilities_mentioned(listing: dict[str, Any]) -> bool:
    text = " ".join(
        str(listing.get(field) or "")
        for field in ("title", "description")
    )
    return bool(UTILITIES_INCLUDED_RE.search(text))


def _move_in_hold_paragraph(listing: dict[str, Any], profile: dict[str, Any]) -> str | None:
    signal, move_in_fit, _ = _move_in_from_flags(listing.get("flags_json"))
    if move_in_fit not in ("risky", "maybe"):
        return None
    listing_date = signal or "the date listed"
    target = profile.get("move_in") or "my target move-in window"
    return (
        f"My target move-in is {target}. I noticed the listing says "
        f"{listing_date}. Would you be open to holding the room until then, "
        f"or is the date firm?"
    )


def _about_lines(profile: dict[str, Any]) -> str:
    about = profile.get("about")
    if not about:
        return ""
    if isinstance(about, list):
        lines = [str(item).strip() for item in about if str(item).strip()]
    else:
        lines = [
            line.strip().lstrip("- ").strip()
            for line in str(about).splitlines()
            if line.strip()
        ]
    if not lines:
        return ""
    return "\n".join(f"- {line}" for line in lines)


def standard_apply_message(
    profile: dict[str, Any],
    listing_url: str = "",
) -> str:
    """Same inquiry text for every listing — template + optional listing URL."""
    custom = (profile.get("message_template") or "").strip()
    if not custom:
        return build_draft({"url": listing_url, "neighborhood": ""}, profile)
    url = (listing_url or "").strip()
    if url and url not in custom:
        blocks = custom.split("\n\n", 1)
        if len(blocks) == 2:
            return f"{blocks[0]}\n\n{url}\n\n{blocks[1]}"
        return f"{custom}\n\n{url}"
    return custom


def build_draft(listing: dict[str, Any], profile: dict[str, Any]) -> str:
    """Build a personalized Craigslist inquiry from profile + listing flags."""
    custom = (profile.get("message_template") or "").strip()
    listing_url = (listing.get("url") or "").strip()
    if custom:
        if listing_url and listing_url not in custom:
            blocks = custom.split("\n\n", 1)
            if len(blocks) == 2:
                paragraphs = [blocks[0], listing_url, blocks[1]]
            else:
                paragraphs = [custom, listing_url]
        else:
            paragraphs = [custom]
        if profile.get("append_hold_question", True):
            hold_paragraph = _move_in_hold_paragraph(listing, profile)
            if hold_paragraph:
                paragraphs.append(hold_paragraph)
        return "\n\n".join(paragraphs)

    hood = listing.get("neighborhood") or "the area"
    name = profile.get("name") or "there"
    one_liner = (profile.get("one_liner") or "").strip()
    move_in = profile.get("move_in") or "soon"
    budget = profile.get("budget") or 1300

    opener = f"Hi! I'm {name}."
    if one_liner:
        opener = f"{opener} {one_liner}."
    opener = (
        f"{opener} I saw your listing for the room in {hood} and I'm interested."
    )

    body = (
        f"I'm looking for a room with a move-in around {move_in}. "
        f"My budget is up to ${budget}/month."
    )

    about_block = _about_lines(profile)
    closing = "Would it be possible to schedule a quick chat or viewing? Thanks!"

    paragraphs = [opener, body]
    if about_block:
        paragraphs.append(about_block)

    hold_paragraph = _move_in_hold_paragraph(listing, profile)
    if hold_paragraph:
        paragraphs.append(hold_paragraph)

    if not _utilities_mentioned(listing):
        paragraphs.append("Are utilities included in the rent?")

    paragraphs.append(closing)
    return "\n\n".join(paragraphs)


def _is_facebook_marketplace_url(url: str) -> bool:
    return "facebook.com" in url and "/marketplace/item/" in url


def resolve_listing(listing_ref: str) -> dict[str, Any] | None:
    """Resolve a listing URL or id to a scored listing row."""
    ref = (listing_ref or "").strip()
    if not ref:
        return None

    if ref.startswith("http://") or ref.startswith("https://"):
        row = get_listing_by_url(ref)
        if row is not None:
            return _listing_with_score(row["id"])
        if _is_facebook_marketplace_url(ref):
            try:
                import filter as listing_filter
                import rank as rank_module
                from scout_facebook import ingest_url

                details = ingest_url(ref)
                listing_filter.run()
                rank_module.run()
                listing = _listing_with_score(details["listing_id"])
                if listing is not None:
                    return listing
            except Exception as exc:
                print(f"Facebook ingest failed: {exc}", file=sys.stderr)
        path = urlparse(ref).path.rstrip("/")
        slug = path.split("/")[-1] if path else ref
        return _listing_with_score(slug)

    listing = _listing_with_score(ref)
    if listing is not None:
        return listing

    row = get_listing_by_id(ref)
    if row is not None:
        return _listing_with_score(row["id"])
    return None


def create_application(listing_id: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build draft text and persist an application row."""
    init_db()
    listing = _listing_with_score(listing_id)
    if listing is None:
        raise ValueError(f"Listing not found: {listing_id}")

    profile_data = profile or load_profile()
    draft_text = build_draft(listing, profile_data)
    channel = default_channel_for_listing(listing)
    app = upsert_application_draft(
        listing_id,
        draft_text,
        status="draft",
        channel=channel,
    )
    return {
        "application": app,
        "listing": listing,
        "draft_text": draft_text,
    }


def format_apply_message(result: dict[str, Any]) -> str:
    """Format application output for CLI or Telegram."""
    listing = result["listing"]
    draft = result["draft_text"]
    title = (listing.get("title") or "Untitled")[:60]
    price = f"${listing['price']}" if listing.get("price") else "N/A"
    hood = listing.get("neighborhood") or "Unknown"
    score = listing.get("score")
    score_bit = f" [{score}]" if score is not None else ""

    if is_facebook_listing(listing):
        paste_hint = "Open the listing → Message seller → paste this draft"
    else:
        paste_hint = "Copy this and paste into Craigslist reply"

    header = (
        f"Apply draft{score_bit}\n"
        f"{title}\n"
        f"{price} · {hood}\n"
        f"{listing.get('url', '')}\n"
        f"{'-' * 40}\n"
        f"{draft}\n"
        f"{'-' * 40}\n"
        f"{paste_hint}"
    )
    return header


def build_tour_questions(listing: dict[str, Any], profile: dict[str, Any] | None = None) -> list[str]:
    """Generate five tour-prep questions for a listing."""
    profile_data = profile or load_profile()
    _, move_in_fit, _ = _move_in_from_flags(listing.get("flags_json"))
    sqft, _, _ = _size_from_flags(listing.get("flags_json"))
    utilities_known = _utilities_mentioned(listing)

    utilities_q = (
        "What utilities are included in rent, and roughly how much do "
        "roommates pay for shared bills (water, gas, electric, internet)?"
        if not utilities_known
        else "You mention utilities — can you confirm what's included vs. split?"
    )

    if sqft is not None and sqft < 100:
        size_q = (
            f"The listing mentions ~{sqft} sq ft — is the room workable for a "
            "full bedroom setup (bed, desk, dresser)?"
        )
    else:
        size_q = "Is there closet or storage space in the room?"

    move_in_q = (
        f"My move-in target is {profile_data.get('move_in', 'mid-August')}. "
        "Is that date workable, and would you hold the room until then?"
        if move_in_fit in ("risky", "maybe", "unknown")
        else f"Is move-in flexible around {profile_data.get('move_in', 'mid-August')}?"
    )

    return [
        utilities_q,
        "What are the house rules (guests, quiet hours, cleaning schedule, shared food)?",
        move_in_q,
        size_q,
        "Who are the other roommates (ages/work schedules), and how long have they lived there?",
    ]


def format_prep_message(listing: dict[str, Any], profile: dict[str, Any] | None = None) -> str:
    """Format tour-prep questions for CLI or Telegram."""
    questions = build_tour_questions(listing, profile)
    title = (listing.get("title") or "Untitled")[:60]
    lines = [
        f"Tour prep — {title}",
        listing.get("url", ""),
        "",
    ]
    for i, question in enumerate(questions, 1):
        lines.append(f"{i}. {question}")
    return "\n".join(lines)


def _cmd_listing_ref(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.top is not None:
        return get_ranked_listing_at_position(args.top)
    if args.listing_ref:
        return resolve_listing(args.listing_ref)
    return get_first_unapplied_ranked_listing()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Draft Craigslist application messages from profile.yaml",
    )
    parser.add_argument(
        "listing_ref",
        nargs="?",
        help="Listing URL (Craigslist/Facebook) or id",
    )
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Draft for the Nth ranked listing (1 = best)",
    )
    ns = parser.parse_args(argv)

    if ns.top is not None and ns.listing_ref:
        print("Use either a listing ref or --top, not both.", file=sys.stderr)
        return 1

    try:
        init_db()
        profile = load_profile()

        if ns.top is not None and ns.top > 1:
            listing = get_ranked_listing_at_position(ns.top)
        elif ns.top == 1 or (ns.top is None and not ns.listing_ref):
            listing = get_first_unapplied_ranked_listing()
        else:
            listing = resolve_listing(ns.listing_ref or "")

        if listing is None:
            print("No matching listing found.", file=sys.stderr)
            return 1

        result = create_application(listing["id"], profile)
        print(format_apply_message(result))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())