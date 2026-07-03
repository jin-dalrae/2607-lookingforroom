"""Batch scoring pipeline and CLI entrypoints."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from config import LOCATION_PREFERENCES

from lfr.db import (
    count_listings,
    get_listings_batch,
    get_unscored_listings,
    init_db,
    save_score,
    seed_test_listings,
)
from lfr.score.criteria import BATCH_SIZE, RENT_PERIOD_VALUES, SIZE_TIER_VALUES
from lfr.score.gemini import _call_gemini, _prompt
from lfr.score.heuristics import _heuristic_score, _pack_flags
from lfr.score.listing_rules import (
    _apply_rent_period_scoring,
    _apply_size_scoring,
    _classify_room_type,
    _classify_size,
    _detect_rent_period,
    _ensure_room_type_flags,
)
from lfr.score.location_rules import _classify_location_tier
from lfr.score.move_in_scoring import _analyze_move_in, _apply_move_in_scoring
from lfr.score.transit import (
    _classify_transit_tier,
    _muni_caltrain_within_10min,
    _transit_tier_flag,
)

def _enrich_size(
    item: dict[str, Any],
    listing_text: str,
) -> None:
    """Apply size detection and scoring to a scored result."""
    size_info = _classify_size(listing_text)

    sqft = item.get("sqft")
    if sqft is not None:
        try:
            size_info["sqft"] = int(sqft)
        except (TypeError, ValueError):
            pass

    size_tier = item.get("size_tier")
    if size_tier in SIZE_TIER_VALUES:
        size_info["size_tier"] = size_tier

    meets = item.get("meets_150_sqft")
    if meets is not None:
        size_info["meets_150_sqft"] = bool(meets)

    flags = item.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]

    score = int(item.get("score", 0))
    reasoning_parts = [str(item.get("reasoning", "")).strip()] if item.get("reasoning") else []
    reasoning_parts = [p for p in reasoning_parts if p]

    score, size_info, flags, reasoning_parts = _apply_size_scoring(
        text=listing_text,
        score=score,
        flags=flags,
        parts=reasoning_parts,
        size_info=size_info,
    )

    item["sqft"] = size_info.get("sqft")
    item["size_tier"] = size_info.get("size_tier", "unknown")
    item["meets_150_sqft"] = size_info.get("meets_150_sqft")
    item["flags"] = flags
    item["score"] = max(0, min(100, score))
    item["reasoning"] = "; ".join(reasoning_parts)[:120]


def _enrich_move_in(
    item: dict[str, Any],
    listing_text: str,
    move_in_date_field: str | None = None,
) -> None:
    """Apply move-in signal parsing and scoring to a scored result."""
    move_in_info = _analyze_move_in(listing_text, move_in_date_field)

    flags = item.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]

    score = int(item.get("score", 0))
    reasoning_parts = [str(item.get("reasoning", "")).strip()] if item.get("reasoning") else []
    reasoning_parts = [p for p in reasoning_parts if p]
    reasoning_parts = [
        p for p in reasoning_parts
        if not any(
            token in p.lower()
            for token in (
                "move-in",
                "move in",
                "aug move-in",
                "landlord may not wait",
                "negotiate hold",
                "confirm with landlord",
            )
        )
    ]

    score, move_in_info, flags, reasoning_parts = _apply_move_in_scoring(
        score=score,
        flags=flags,
        parts=reasoning_parts,
        move_in_info=move_in_info,
    )

    item["move_in_signal"] = move_in_info.get("move_in_signal")
    item["move_in_fit"] = move_in_info.get("move_in_fit", "unknown")
    item["landlord_wait_likely"] = move_in_info.get("landlord_wait_likely")
    item["move_in_compatible"] = move_in_info.get("move_in_fit") in ("ideal", "maybe")
    item["flags"] = flags
    item["score"] = max(0, min(100, score))
    item["reasoning"] = "; ".join(reasoning_parts)[:120]


def _enrich_rent_period(
    item: dict[str, Any],
    listing_text: str,
    price: int | None,
    *,
    title: str = "",
) -> None:
    """Apply rent-period detection and penalties to a scored result."""
    rent_period = item.get("rent_period")
    short_term_reject = bool(item.get("short_term_reject"))

    if rent_period not in RENT_PERIOD_VALUES:
        rent_period, short_term_reject = _detect_rent_period(listing_text, price, title=title)
    elif rent_period in ("weekly", "daily", "sublet"):
        short_term_reject = True
    elif not short_term_reject:
        _, short_term_reject = _detect_rent_period(listing_text, price, title=title)

    flags = item.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]

    score = int(item.get("score", 0))
    reasoning_parts = [str(item.get("reasoning", "")).strip()] if item.get("reasoning") else []
    reasoning_parts = [p for p in reasoning_parts if p]

    score, rent_period, short_term_reject, flags, reasoning_parts = _apply_rent_period_scoring(
        text=listing_text,
        price=price,
        score=score,
        flags=flags,
        parts=reasoning_parts,
        title=title,
        rent_period=str(rent_period) if rent_period in RENT_PERIOD_VALUES else None,
        short_term_reject=short_term_reject,
    )

    item["rent_period"] = rent_period
    item["short_term_reject"] = short_term_reject
    item["flags"] = flags
    item["score"] = score
    item["reasoning"] = "; ".join(reasoning_parts)[:120]


def score_batch(batch: list[dict[str, Any]], use_gemini: bool = True) -> list[dict[str, Any]]:
    from lfr.listings.description import is_facebook_scoring_ready

    batch = [row for row in batch if is_facebook_scoring_ready(row)]
    if not batch:
        return []
    if use_gemini:
        try:
            data = _call_gemini(_prompt(batch))
            results = data.get("results", [])
            # Ensure transit_adjacent flag is set when Gemini mentions transit in flags/reasoning
            id_to_row = {str(r["id"]): r for r in batch}
            id_to_text = {
                listing_id: " ".join(
                    str(r.get(k, "")) for k in ("title", "description", "neighborhood")
                ).lower()
                for listing_id, r in id_to_row.items()
            }
            for item in results:
                flags = item.get("flags") or []
                if not isinstance(flags, list):
                    flags = [str(flags)]
                listing_text = id_to_text.get(str(item.get("id")), "")
                transit_tier, muni_line = _classify_transit_tier(listing_text)
                tier_flag = _transit_tier_flag(transit_tier)
                if tier_flag and tier_flag not in flags:
                    flags.append(tier_flag)
                reasoning = str(item.get("reasoning", "")).lower()
                combined_text = f"{listing_text} {reasoning}"
                if transit_tier in ("muni_tram", "caltrain") and _muni_caltrain_within_10min(
                    combined_text
                ):
                    if "transit_10min_bonus" not in flags:
                        flags.append("transit_10min_bonus")
                    if "transit_adjacent" not in flags:
                        flags.append("transit_adjacent")
                elif transit_tier == "muni_bus" and "transit_adjacent" not in flags:
                    flags.append("transit_adjacent")
                item["flags"] = flags
                item["transit_tier"] = transit_tier
                item["transit_detail"] = muni_line
                source_row = id_to_row.get(str(item.get("id")), {})
                loc_tier, loc_adj, loc_flag = _classify_location_tier(
                    listing_text,
                    neighborhood=str(source_row.get("neighborhood") or ""),
                    title=str(source_row.get("title") or ""),
                    url=str(source_row.get("url") or ""),
                )
                item["location_tier"] = loc_tier
                if loc_flag and loc_flag not in flags:
                    flags.append(loc_flag)
                    item["flags"] = flags
                if loc_adj and loc_tier in LOCATION_PREFERENCES["tiers"]:
                    item["score"] = max(0, min(100, int(item.get("score", 0)) + loc_adj))
                elif loc_adj and loc_tier in LOCATION_PREFERENCES["penalize"]:
                    item["score"] = max(0, min(100, int(item.get("score", 0)) + loc_adj))
                _ensure_room_type_flags(item, listing_text)
                _enrich_rent_period(
                    item,
                    listing_text,
                    source_row.get("price"),
                    title=str(source_row.get("title") or ""),
                )
                _enrich_size(item, listing_text)
                _enrich_move_in(item, listing_text, source_row.get("move_in_date"))
            return results
        except Exception as exc:
            print(f"  warning: Gemini unavailable ({exc}); using heuristic scorer.", file=sys.stderr)
    return [_heuristic_score(row) for row in batch]


def apply_results(results: list[dict[str, Any]]) -> int:
    saved = 0
    for item in results:
        listing_id = item.get("id")
        if not listing_id:
            continue
        raw_flags = item.get("flags", [])
        if not isinstance(raw_flags, list):
            raw_flags = [str(raw_flags)]
        transit_tier = str(item.get("transit_tier") or "none")
        transit_detail = item.get("transit_detail")
        location_tier = str(item.get("location_tier") or "none")
        rent_period = str(item.get("rent_period") or "unknown")
        short_term_reject = bool(item.get("short_term_reject", False))
        sqft_raw = item.get("sqft")
        sqft = int(sqft_raw) if sqft_raw is not None else None
        size_tier = str(item.get("size_tier") or "unknown")
        meets_raw = item.get("meets_150_sqft")
        meets_150_sqft = bool(meets_raw) if meets_raw is not None else None
        move_in_fit = str(item.get("move_in_fit") or "unknown")
        landlord_raw = item.get("landlord_wait_likely")
        landlord_wait_likely = (
            bool(landlord_raw) if landlord_raw is not None else None
        )
        save_score(
            listing_id=str(listing_id),
            score=int(item.get("score", 0)),
            is_private_room=bool(item.get("is_private_room", False)),
            is_scam_likely=bool(item.get("is_scam_likely", False)),
            move_in_compatible=bool(item.get("move_in_compatible", False)),
            flags=_pack_flags(
                raw_flags,
                transit_tier,
                transit_detail,
                location_tier=location_tier,
                rent_period=rent_period,
                short_term_reject=short_term_reject,
                sqft=sqft,
                size_tier=size_tier,
                meets_150_sqft=meets_150_sqft,
                move_in_signal=item.get("move_in_signal"),
                move_in_fit=move_in_fit,
                landlord_wait_likely=landlord_wait_likely,
            ),
            reasoning=str(item.get("reasoning", "")),
        )
        saved += 1
    return saved


def _score_listings(
    listings: list[dict[str, Any]],
    *,
    use_gemini: bool = True,
    label: str = "listing",
) -> int:
    total = 0
    for offset in range(0, len(listings), BATCH_SIZE):
        batch = listings[offset : offset + BATCH_SIZE]
        print(f"Scoring batch of {len(batch)} {label}(s)…")
        results = score_batch(batch, use_gemini=use_gemini)
        n = apply_results(results)
        total += n
        print(f"  → saved {n} score(s)")
    return total


def run(*, rescore_all: bool = False, use_gemini: bool = True) -> int:
    """Score listings. Returns total scored."""
    init_db()
    if count_listings() == 0:
        print("No listings found — seeding 3 test listings.")
        seed_test_listings()

    if rescore_all:
        total = 0
        offset = 0
        while True:
            batch = get_listings_batch(offset=offset, limit=BATCH_SIZE)
            if not batch:
                break
            total += _score_listings(batch, use_gemini=use_gemini, label="listing")
            offset += len(batch)
            if len(batch) < BATCH_SIZE:
                break
        return total

    total = 0
    while True:
        batch = get_unscored_listings(limit=BATCH_SIZE)
        if not batch:
            break
        total += _score_listings(batch, use_gemini=use_gemini, label="unscored listing")
        if len(batch) < BATCH_SIZE:
            break
    return total


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score room listings against user criteria.")
    parser.add_argument(
        "--rescore-all",
        action="store_true",
        help="Re-score every listing in the database (not only unscored).",
    )
    parser.add_argument(
        "--heuristic-only",
        action="store_true",
        help="Skip Gemini API and use local heuristic scorer only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        total = run(rescore_all=args.rescore_all, use_gemini=not args.heuristic_only)
        if total == 0:
            print("No listings to process.")
        else:
            action = "Re-scored" if args.rescore_all else "Scored"
            print(f"Done. {action} {total} listing(s).")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())