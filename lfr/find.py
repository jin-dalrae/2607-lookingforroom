"""Gemini find over the current listing queue (no web search)."""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from lfr.config import AI_MODEL, GEMINI_API_KEY

_MODELS = [
    (AI_MODEL or "").strip().strip("'\""),
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.5-flash-lite",
]

_MAX_LISTINGS = 220
_MAX_DETAILS = 280
_MAX_QUESTION = 400


def gemini_configured() -> bool:
    return bool(GEMINI_API_KEY)


def compact_listing(item: dict[str, Any]) -> dict[str, Any]:
    details = str(item.get("details") or item.get("description") or "").strip()
    if len(details) > _MAX_DETAILS:
        details = details[:_MAX_DETAILS].rstrip() + "…"
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or "")[:120],
        "price": item.get("price"),
        "neighborhood": str(item.get("neighborhood") or item.get("displayAddress") or "")[:80],
        "address": str(item.get("displayAddress") or item.get("rentalAddress") or "")[:80],
        "layout": str(item.get("layoutLabel") or ""),
        "bath": str(item.get("bathPrivacy") or ""),
        "sqft": str(item.get("sqftLabel") or ""),
        "moveIn": str(item.get("moveInLabel") or ""),
        "source": str(item.get("source") or ""),
        "score": item.get("score"),
        "poster": str(item.get("posterName") or ""),
        "roomsInHouse": int(item.get("roomsInHouse") or item.get("roomsListed") or 1),
        "details": details,
    }


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _call_gemini_rest(prompt: str) -> dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini API key is not configured")
    last_err: Exception | None = None
    for model in _MODELS:
        if not model:
            continue
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        try:
            response = requests.post(
                url,
                params={"key": GEMINI_API_KEY},
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=45,
            )
            if response.status_code >= 400:
                last_err = RuntimeError(f"{model} HTTP {response.status_code}")
                continue
            payload = response.json()
            parts = (
                payload.get("candidates")
                or [{}]
            )[0].get("content", {}).get("parts") or []
            text = "".join(str(part.get("text") or "") for part in parts)
            if not text.strip():
                last_err = RuntimeError(f"{model} empty response")
                continue
            return _parse_json_text(text)
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"Gemini find failed: {last_err}")


def _build_prompt(question: str, listings: list[dict[str, Any]]) -> str:
    return (
        "Filter this housing-search queue. Use ONLY the listings JSON below. "
        "Do not use the web or outside knowledge. Do not invent listings.\n\n"
        f"QUESTION:\n{question}\n\n"
        "LISTINGS:\n"
        f"{json.dumps(listings, ensure_ascii=False)}\n\n"
        "Return JSON only:\n"
        '{ "ids": ["listing-id", ...], "note": "one short sentence" }\n'
        "Include every listing that matches. If a house has 2+ rooms available "
        "(roomsInHouse >= 2, or details/author say multiple rooms), treat those "
        "as the same house when the question asks about multiple rooms. "
        "If nothing matches, return {\"ids\": [], \"note\": \"No matching listings.\"}."
    )


def find_listings(question: str, listings: list[dict[str, Any]]) -> dict[str, Any]:
    query = (question or "").strip()
    if not query:
        raise ValueError("Type a question first")
    if len(query) > _MAX_QUESTION:
        query = query[:_MAX_QUESTION].rstrip()

    known_ids: set[str] = set()
    compact: list[dict[str, Any]] = []
    for item in listings[:_MAX_LISTINGS]:
        row = compact_listing(item)
        listing_id = row["id"]
        if not listing_id or listing_id in known_ids:
            continue
        known_ids.add(listing_id)
        compact.append(row)
    if not compact:
        return {"ids": [], "note": "No listings loaded."}

    parsed = _call_gemini_rest(_build_prompt(query, compact))
    raw_ids = parsed.get("ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    ids = [str(listing_id) for listing_id in raw_ids if str(listing_id) in known_ids]
    note = str(parsed.get("note") or "").strip()
    if not note:
        note = f"{len(ids)} matching listing(s)." if ids else "No matching listings."
    return {"ids": ids, "note": note[:240]}
