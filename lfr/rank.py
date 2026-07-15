#!/usr/bin/env python3
"""Output top-ranked listings and write digest.md."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lfr.config import LOCATION_PREFERENCES, TRANSIT_PREFERENCES
from lfr.db import get_matching_listings, init_db

from lfr.paths import PROJECT_ROOT
DIGEST_PATH = PROJECT_ROOT / "digest.md"
TOP_N = 15

ROOM_TYPE_VALUES = (
    "private_bedroom",
    "shared_house_ok",
    "shared_bedroom_reject",
    "sro_reject",
)

TRANSIT_TIER_LABELS = {
    tier: cfg["digest_label"]
    for tier, cfg in TRANSIT_PREFERENCES["tiers"].items()
}

LOCATION_TIER_LABELS = {
    tier: cfg["digest_label"]
    for tier, cfg in LOCATION_PREFERENCES["tiers"].items()
}
LOCATION_TIER_LABELS.update(
    {
        tier: cfg["digest_label"]
        for tier, cfg in LOCATION_PREFERENCES["penalize"].items()
    }
)


def _parse_flags_payload(
    flags_json: str | None,
) -> tuple[list[str], str, str | None, str, bool]:
    """Return (flags, transit_tier, transit_detail, rent_period, short_term_reject)."""
    if not flags_json:
        return [], "none", None, "unknown", False
    try:
        parsed = json.loads(flags_json)
    except (json.JSONDecodeError, TypeError):
        return [], "none", None, "unknown", False

    if isinstance(parsed, dict):
        flags = parsed.get("flags") or []
        if not isinstance(flags, list):
            flags = [str(flags)]
        tier = str(parsed.get("transit_tier") or "none")
        detail = parsed.get("transit_detail")
        rent_period = str(parsed.get("rent_period") or "unknown")
        short_term_reject = bool(parsed.get("short_term_reject"))
        if rent_period in ("weekly", "daily"):
            short_term_reject = True
        return (
            [str(f) for f in flags],
            tier,
            str(detail) if detail else None,
            rent_period,
            short_term_reject,
        )

    if isinstance(parsed, list):
        return [str(f) for f in parsed], "none", None, "unknown", False

    return [], "none", None, "unknown", False


def _move_in_from_flags(
    flags_json: str | None,
) -> tuple[str | None, str, bool | None]:
    """Return (move_in_signal, move_in_fit, landlord_wait_likely)."""
    if not flags_json:
        return None, "unknown", None
    try:
        parsed = json.loads(flags_json)
    except (json.JSONDecodeError, TypeError):
        return None, "unknown", None

    if not isinstance(parsed, dict):
        return None, "unknown", None

    signal = parsed.get("move_in_signal")
    move_in_fit = str(parsed.get("move_in_fit") or "unknown")
    landlord_raw = parsed.get("landlord_wait_likely")
    landlord_wait_likely = bool(landlord_raw) if landlord_raw is not None else None
    return (str(signal) if signal else None, move_in_fit, landlord_wait_likely)


def _move_in_display(flags_json: str | None) -> str | None:
    """Human-readable move-in line for digest/bot output."""
    signal, move_in_fit, landlord_wait = _move_in_from_flags(flags_json)
    label = signal or "unspecified"

    suffixes = {
        "ideal": "Aug 1–18 ✓",
        "maybe": "outside window",
        "risky": "excluded",
        "too_early": "before August",
        "too_late": "after Aug 18",
        "unknown": "excluded",
    }
    suffix = suffixes.get(move_in_fit, move_in_fit)
    if move_in_fit == "risky" and landlord_wait is False:
        suffix = "⚠️ unlikely to wait"
    return f"Move-in: {label} ({suffix})"


def _size_from_flags(flags_json: str | None) -> tuple[int | None, str, bool | None]:
    """Return (sqft, size_tier, meets_150_sqft)."""
    if not flags_json:
        return None, "unknown", None
    try:
        parsed = json.loads(flags_json)
    except (json.JSONDecodeError, TypeError):
        return None, "unknown", None

    if not isinstance(parsed, dict):
        return None, "unknown", None

    sqft_raw = parsed.get("sqft")
    sqft: int | None
    try:
        sqft = int(sqft_raw) if sqft_raw is not None else None
    except (TypeError, ValueError):
        sqft = None

    size_tier = str(parsed.get("size_tier") or "unknown")
    meets_raw = parsed.get("meets_150_sqft")
    meets_150_sqft = bool(meets_raw) if meets_raw is not None else None
    return sqft, size_tier, meets_150_sqft


def _size_display(flags_json: str | None) -> str | None:
    """Human-readable size line for digest/bot output."""
    sqft, size_tier, _ = _size_from_flags(flags_json)
    if sqft is not None:
        if sqft < 100:
            return f"Size: ~{sqft} sqft ⚠️ (under 100)"
        return f"Size: ~{sqft} sqft"
    if size_tier == "large":
        return "Size: large (no sqft stated)"
    return None


def _rent_period_display(rent_period: str) -> str | None:
    labels = {
        "monthly": "monthly",
        "weekly": "weekly (short-term)",
        "daily": "daily/nightly (short-term)",
    }
    return labels.get(rent_period)


def _transit_adjacent(row: dict) -> bool:
    flags, tier, _, _, _ = _parse_flags_payload(row.get("flags_json"))
    if tier != "none":
        return True
    if "transit_adjacent" in flags:
        return True
    reasoning = (row.get("reasoning") or "").lower()
    return any(term in reasoning for term in ("bart", "muni", "caltrain", "transit", "metro", "streetcar"))


def _transit_tier(row: dict) -> str:
    _, tier, _, _, _ = _parse_flags_payload(row.get("flags_json"))
    if tier != "none":
        return tier
    reasoning = (row.get("reasoning") or "").lower()
    if any(t in reasoning for t in ("n-judah", "j-church", "streetcar", "muni metro", "tram", "light rail")):
        return "muni_tram"
    if "caltrain" in reasoning:
        return "caltrain"
    if "bart" in reasoning:
        return "bart"
    if "muni" in reasoning or "bus" in reasoning:
        return "muni_bus"
    return "none"


def _location_tier(row: dict) -> str:
    if not row.get("flags_json"):
        return "none"
    try:
        parsed = json.loads(row["flags_json"])
    except (json.JSONDecodeError, TypeError):
        return "none"
    if isinstance(parsed, dict):
        return str(parsed.get("location_tier") or "none")
    return "none"


def _location_label(row: dict) -> str | None:
    tier = _location_tier(row)
    if tier == "none":
        return None
    return LOCATION_TIER_LABELS.get(tier, tier)


def _transit_label(row: dict) -> str | None:
    _, tier, detail, _, _ = _parse_flags_payload(row.get("flags_json"))
    if tier == "none":
        tier = _transit_tier(row)
    if tier == "none":
        return None
    label = TRANSIT_TIER_LABELS.get(tier, tier)
    if tier == "muni_tram" and detail:
        return f"{label} ({detail})"
    return label


def _room_type(row: dict) -> str | None:
    flags, _, _, _, _ = _parse_flags_payload(row.get("flags_json"))
    for flag in flags:
        if flag in ROOM_TYPE_VALUES:
            return flag
    return None


def _room_type_label(room_type: str | None) -> str:
    labels = {
        "private_bedroom": "private bedroom",
        "shared_house_ok": "small shared house OK",
        "shared_bedroom_reject": "shared bedroom (reject)",
        "sro_reject": "SRO/hostel (reject)",
    }
    return labels.get(room_type or "", room_type or "unknown")


def _format_row(row: dict, rank: int) -> str:
    price = f"${row['price']}" if row.get("price") else "N/A"
    _, _, _, rent_period, _ = _parse_flags_payload(row.get("flags_json"))
    rent_period_line = ""
    period_label = _rent_period_display(rent_period)
    if period_label:
        rent_period_line = f"- **Rent period:** {period_label}\n"
    transit_line = ""
    transit_label = _transit_label(row)
    if transit_label:
        transit_line = f"- **Near:** {transit_label}\n"
    location_line = ""
    location_label = _location_label(row)
    if location_label:
        location_line = f"- **Location fit:** {location_label}\n"
    room_type = _room_type(row)
    room_type_line = f"- **Room type:** {_room_type_label(room_type)}\n"
    size_line = ""
    size_label = _size_display(row.get("flags_json"))
    if size_label:
        size_line = f"- **{size_label}**\n"
    move_in_line = ""
    move_in_label = _move_in_display(row.get("flags_json"))
    if move_in_label:
        move_in_line = f"- **{move_in_label}**\n"
    return (
        f"### {rank}. {row.get('title', 'Untitled')}\n"
        f"- **Price:** {price}\n"
        f"{rent_period_line}"
        f"- **Neighborhood:** {row.get('neighborhood') or 'Unknown'}\n"

        f"{room_type_line}"
        f"{size_line}"
        f"{move_in_line}"
        f"{location_line}"
        f"{transit_line}"
        f"- **Reasoning:** {row.get('reasoning', '')}\n"
        f"- **URL:** {row.get('url', '')}\n"
    )


def write_digest(rows: list[dict]) -> None:
    lines = [
        "# Room Search Digest\n",
        f"Top {len(rows)} **matches** (hard filters — no score ranking).\n",
        "Move-in **August 1 – Aug 18**. Rent up to **$1300** ($800–$1000 preferred). "
        "Excluded: Excelsior, Oakland east, scams, short-term, unknown dates, 'available now'. "
        "Sorted: sweet-spot band first, then price. Private bedroom or small shared house.\n",
        "---\n",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(_format_row(row, i))
        lines.append("")
    DIGEST_PATH.write_text("\n".join(lines), encoding="utf-8")


def print_rankings(rows: list[dict]) -> None:
    if not rows:
        print("No matches found. Run `python filter.py --rescore-all` then check criteria.")
        return

    print(f"\n{'=' * 60}")
    print(f"MATCHES ({len(rows)}) — Aug 1–18, ≤$1300, no Excelsior/Oakland east")
    print(f"{'=' * 60}\n")

    for i, row in enumerate(rows, 1):
        price = f"${row['price']}" if row.get("price") else "N/A"
        title = (row.get("title") or "Untitled")[:55]
        source_tag = " 📘" if (row.get("source") or "") == "facebook" else ""
        reasoning = (row.get("reasoning") or "")[:75]
        transit_label = _transit_label(row)
        transit = f" [Near: {transit_label}]" if transit_label else ""
        location_label = _location_label(row)
        location_tag = f" [{location_label}]" if location_label else ""
        room_type = _room_type(row)
        room_tag = f" [{_room_type_label(room_type)}]" if room_type else ""
        size_label = _size_display(row.get("flags_json"))
        size_tag = f" [{size_label}]" if size_label else ""
        move_in_label = _move_in_display(row.get("flags_json"))
        move_in_tag = f" [{move_in_label}]" if move_in_label else ""
        tier = _transit_tier(row)
        tier_tag = f" ({tier})" if tier != "none" else ""
        print(
            f"{i:2}. {title}{source_tag}{room_tag}{size_tag}"
            f"{move_in_tag}{location_tag}{transit}{tier_tag}"
        )
        print(f"    {price} | {row.get('neighborhood', '?')} | {reasoning}")
        print(f"    {row.get('url', '')}\n")


def run() -> int:
    """Return number of listings written to digest."""
    init_db()
    rows = get_matching_listings(limit=TOP_N, exclude_scams=True)
    print_rankings(rows)
    write_digest(rows)
    print(f"Wrote digest to {DIGEST_PATH}")
    return len(rows)


def main() -> int:
    try:
        run()
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())