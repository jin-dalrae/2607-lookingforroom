"""Optional Gemini API batch scoring (off by default — heuristics are enough)."""

from __future__ import annotations

import json
import re
from typing import Any

from lfr.config import AI_MODEL, GCP_KEY, GENERATIVE_LANGUAGE_API_KEY

from lfr.score.criteria import CRITERIA, MODEL_FALLBACKS


def _api_key() -> str:
    for key in (GCP_KEY, GENERATIVE_LANGUAGE_API_KEY):
        if key and key.strip():
            return key.strip()
    raise RuntimeError(
        "Gemini scoring needs GCP_KEY (or generative_language_api_key) in .env "
        "and USE_GEMINI=1. Default scoring uses local heuristics only."
    )


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": (row.get("title") or "")[:120],
        "price": row.get("price"),
        "neighborhood": row.get("neighborhood"),
        "move_in": row.get("move_in_date"),
        "desc": (row.get("description") or "")[:300],
    }


def _prompt(batch: list[dict[str, Any]]) -> str:
    return f"""Score each rental listing against the user criteria. Return ONLY valid JSON.

USER CRITERIA:
{json.dumps(CRITERIA, indent=2)}

LISTINGS:
{json.dumps([_compact(r) for r in batch], indent=2)}

Output schema:
{{
  "results": [
    {{
      "id": "<listing id string>",
      "score": <0-100>,
      "is_private_room": <bool — true if own private bedroom, not shared bedroom>,
      "room_type": "<private_bedroom|shared_house_ok|shared_bedroom_reject|sro_reject>",
      "is_scam_likely": <bool>,
      "move_in_compatible": <bool>,
      "rent_period": "<monthly|weekly|daily|unknown>",
      "short_term_reject": <bool — true if weekly/daily/sublet, not a monthly lease>,
      "sqft": <number or null — parse from "150 sq ft", "10x15", etc.>,
      "size_tier": "<large|ok|small|unknown>",
      "meets_150_sqft": <true|false|null — null if size unknown>,
      "flags": ["short", "tags — include muni_tram_adjacent, caltrain_adjacent, bart_adjacent, muni_bus_only, transit_adjacent, small_household, short_term_reject, meets_150_sqft, small_room_signal, large_room_signal when applicable"],
      "reasoning": "<one line, max 120 chars>"
    }}
  ]
}}

Scoring guidance:
- Reject commercial office/workspace subleases (office sublease, coworking, shared workspace, desk rental). Residential rooms with a home office nook are OK.
- Reject short residential subleases/sublets: single-month sublets, a few weeks, fixed night counts, "flat for the stay", date ranges under ~2 months. Long-term sublets are OK.
- Reject listings advertised primarily in Spanish (habitación, se renta cuarto, etc.) unless the title clearly includes English room-for-rent wording.
- User needs MONTHLY rent only. Detect rent period from title/description/price:
  weekly signals: "per week", "/week", "weekly", "wk", "a week", "$650/week"
  daily/nightly: "per night", "/night", "daily", "nightly", "$49/day", "airbnb"
  monthly signals: "per month", "/month", "monthly", "/mo", "per mo"
  Set short_term_reject=true and cap score at 30 for weekly/daily/sublets.
  If price < $400 in SF/Oakland without explicit monthly, treat as suspicious short-term.
  In reasoning, note effective monthly (~weekly*4.33) when period is weekly/daily.
- Accept private bedroom OR own room in small shared house (~3 people, shared kitchen/bath OK).
- Do NOT penalize shared kitchen/bathroom/house — only reject shared BEDROOM, SRO/hostel, curtain rooms.
- Boost small households: 3br, 2 roommates, 3-person house (add flag small_household).
- Transit bonus ONLY when Muni Metro/tram or Caltrain is within 10 minutes walk (+transit_10min_bonus, +muni_tram_adjacent or +caltrain_adjacent). NOT BART — tag bart_adjacent but no boost. Generic Muni bus (+muni_bus_only) is weaker.
- User is currently in SOMA and prefers SF city center: boost SOMA/South Beach/Mission Bay (+soma_adjacent), Financial District/Embarcadero/Civic Center (+city_center), focus core (+focus_core).
- Homes near Caltrain stations work too: tag +caltrain_adjacent and +caltrain_corridor for 4th & King, Bayshore, Dogpatch, or explicit "near Caltrain" / walk-to-station language in SF. Hard-reject South San Francisco (separate city).
- Hard-reject all Oakland and Emeryville.
- Prioritize August move-in (Aug 2–Sep 1 ideal; early August maybe). Deprioritize "available now" and unknown dates.
- Hard-reject outer SF: Richmond, Sunset/Parkside, Ingleside, Excelsior. Prefer Dogpatch, Noe Valley, Mission, Hayes Valley, Castro, Bernal Heights, near Panhandle, Marina, Chinatown, North Beach, Russian Hill, downtown/SOMA. Bayview still far.
- Penalize Berkeley and all East Bay.
- Penalize Daly City unless clearly BART-adjacent.
- Room size: only penalize explicit sqft under 100. 150+ sq ft is a nice-to-have, not required.
  Parse sqft from title/description: "150 sq ft", "150sqft", "150 square feet", "10x15" (compute 150).
  "Small room", "tiny room", "cozy room" keywords are neutral — do not penalize.
  Large signals (mild boost): "large room", "spacious", "big bedroom", "master bedroom", "huge room", "generous".
  Scoring: explicit sqft >=150 → +5, meets_150_sqft=true; sqft 100–149 → neutral; sqft <100 → cap score at 40;
  large keywords without sqft → +5, size_tier=large. Unknown size → neutral (no penalty).
- 90+ excellent, 70-89 good, 50-69 marginal, <50 poor/scam."""


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _call_gemini(prompt: str) -> dict[str, Any]:
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError(
            "google-generativeai is not installed. "
            "Default scoring needs no AI package; for Gemini install "
            "`pip install google-generativeai` and set USE_GEMINI=1."
        ) from exc

    genai.configure(api_key=_api_key())
    last_err: Exception | None = None

    for model_name in MODEL_FALLBACKS:
        if not model_name:
            continue
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            return _parse_json(response.text)
        except Exception as exc:
            last_err = exc
            continue

    raise RuntimeError(f"All Gemini models failed: {last_err}")
