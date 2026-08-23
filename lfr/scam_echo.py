"""Flag current listings that echo user-marked scams from the $1300 search."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from lfr.listings.poster import extract_poster_name
from lfr.paths import PROJECT_ROOT

# Craigslist / Facebook IDs the user marked Scam on the original $1300 hunt (D1 listing_flags).
KNOWN_SCAM_IDS = frozenset(
    {
        "7955263290",
        "7954116739",
        "7955149789",
        "7955110120",
        "7955103446",
        "7953453294",
        "7954343076",
        "7953783040",
        "7954120983",
        "7953924445",
        "7954245535",
        "7954251785",
        "7953922046",
        "7954211780",
        "7953904223",
        "7953904329",
        "7952821770",
        "7951087897",
        "7953865636",
        "7954260252",
        "7953989388",
        "7953952516",
        "7953869748",
        "7953860148",
        "7953445678",
        "7953107178",
        "7952614617",
        "7950576761",
        "7950150085",
        "7951952505",
        "7950965386",
        "7955252130",
        "7955224672",
        "7955223241",
        "7955127038",
        "7955126612",
        "fb-1427923426102483",
        "fb-1347664030902254",
        "fb-1535303117909930",
        "fb-2102046374028898",
    }
)

_STOP = frozenset(
    {
        "about",
        "apartment",
        "available",
        "bathroom",
        "bedroom",
        "building",
        "contact",
        "included",
        "kitchen",
        "listing",
        "location",
        "please",
        "private",
        "recently",
        "rental",
        "san",
        "francisco",
        "shared",
        "spacious",
        "unit",
        "posted",
    }
)

_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
_TEMPLATE_PHRASES = (
    "drop your phone number, and we'll contact you soon",
    "drop your phone number and we'll contact you soon",
    "get 2 weeks free rent",
    "limited-time offer",
)

_DB_CANDIDATES = (
    PROJECT_ROOT / "data" / "central" / "listings.db",
    PROJECT_ROOT / "listings.db",
    PROJECT_ROOT / "data" / "original" / "listings.db",
)


def _words(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return {w for w in cleaned.split() if len(w) > 4} - _STOP


def _blob(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("title", "description", "details", "detailsRaw", "neighborhood")
    )


def _load_seed_rows() -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in _DB_CANDIDATES:
        if not path.is_file():
            continue
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            placeholders = ",".join("?" for _ in KNOWN_SCAM_IDS)
            fetched = conn.execute(
                f"SELECT id, title, description, price, neighborhood, source, url FROM listings WHERE id IN ({placeholders})",
                tuple(KNOWN_SCAM_IDS),
            ).fetchall()
            for raw in fetched:
                row = dict(raw)
                rows[str(row["id"])] = row
        except sqlite3.Error:
            continue
        finally:
            conn.close()
    return list(rows.values())


def _fingerprint(row: dict[str, Any]) -> dict[str, Any]:
    blob = _blob(row)
    return {
        "id": str(row.get("id") or ""),
        "title": str(row.get("title") or "").strip().lower(),
        "words": _words(blob),
        "phones": {m.replace(" ", "") for m in _PHONE_RE.findall(blob.lower())},
        "emails": {m.lower() for m in _EMAIL_RE.findall(blob)},
        "poster": (extract_poster_name(row) or "").strip().lower(),
        "price": row.get("price"),
    }


def _seeds() -> list[dict[str, Any]]:
    return [_fingerprint(row) for row in _load_seed_rows()]


def match_known_scam(item: dict[str, Any], seeds: list[dict[str, Any]] | None = None) -> str:
    """Return a short reason if this listing echoes a marked scam, else ''."""
    listing_id = str(item.get("id") or "")
    if listing_id in KNOWN_SCAM_IDS:
        return "same listing you marked as scam in the $1300 search"
    alt = listing_id[3:] if listing_id.startswith("fb-") else f"fb-{listing_id}"
    if alt in KNOWN_SCAM_IDS:
        return "same listing you marked as scam in the $1300 search"

    blob = _blob(item).lower()
    for phrase in _TEMPLATE_PHRASES:
        if phrase in blob:
            return "same scam template as a marked $1300 listing"

    fp = _fingerprint(
        {
            "id": listing_id,
            "title": item.get("title"),
            "description": item.get("detailsRaw") or item.get("details") or item.get("description"),
            "price": item.get("price"),
            "neighborhood": item.get("neighborhood"),
            "source": item.get("source"),
            "url": item.get("url"),
        }
    )
    seed_fps = seeds if seeds is not None else _seeds()
    title = fp["title"]
    words = fp["words"]
    for seed in seed_fps:
        if fp["poster"] and seed["poster"] and fp["poster"] == seed["poster"]:
            return f"same poster as marked scam ({fp['poster']})"
        if fp["phones"] and seed["phones"] and fp["phones"] & seed["phones"]:
            return "same phone number as a marked scam"
        if fp["emails"] and seed["emails"] and fp["emails"] & seed["emails"]:
            return "same email as a marked scam"
        seed_words = seed["words"]
        if not words or not seed_words:
            continue
        shared = words & seed_words
        union = words | seed_words
        jaccard = len(shared) / len(union)
        seed_title = seed["title"]
        if jaccard >= 0.72 and len(shared) >= 8:
            return f"very similar text to marked scam {seed['id']}"
        if (
            jaccard >= 0.55
            and len(shared) >= 12
            and title
            and seed_title
            and (title == seed_title or title in seed_title or seed_title in title)
        ):
            return f"similar title and text to marked scam {seed['id']}"
    return ""


def annotate_scam_echo(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds = _seeds()
    for item in listings:
        why = match_known_scam(item, seeds)
        item["scamLikely"] = bool(why)
        item["scamWhy"] = why
    return listings
