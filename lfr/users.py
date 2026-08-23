"""Multi-user profiles, request-scoped active user, and per-user databases."""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from lfr.paths import PROJECT_ROOT

PROFILES_DIR = PROJECT_ROOT / "profiles"
DATA_DIR = PROJECT_ROOT / "data"
ACTIVE_USER_FILE = PROJECT_ROOT / ".active-user"
LEGACY_PROFILE_PATH = PROJECT_ROOT / "profile.yaml"
LEGACY_DB_PATH = PROJECT_ROOT / "listings.db"

DEFAULT_USER_ID = "central"
ORIGINAL_USER_ID = "original"

_request_user_id: ContextVar[str | None] = ContextVar("lfr_request_user_id", default=None)
_users_cache: dict[str, dict[str, Any]] | None = None


def set_request_user_id(user_id: str | None) -> Token:
    return _request_user_id.set(user_id)


def reset_request_user_id(token: Token) -> None:
    _request_user_id.reset(token)


def _slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or "").strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or DEFAULT_USER_ID


def _as_date(value: Any, fallback: date | None = None) -> date | None:
    if value is None or value == "":
        return fallback
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return fallback


def ensure_profiles() -> None:
    """Write bundled profile YAMLs if the profiles directory is empty."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(PROFILES_DIR.glob("*.yaml")) + list(PROFILES_DIR.glob("*.yml"))
    if existing:
        return
    # Profiles are expected in-repo; this is a safety net for a wiped folder.
    (PROFILES_DIR / f"{ORIGINAL_USER_ID}.yaml").write_text(
        "id: original\nname: August search\nsearch_preset: original\n",
        encoding="utf-8",
    )
    (PROFILES_DIR / f"{DEFAULT_USER_ID}.yaml").write_text(
        "id: central\nname: Haneul\nbudget: 1500\n",
        encoding="utf-8",
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile format in {path}")
    return data


def _overlay_legacy_identity(raw: dict[str, Any]) -> dict[str, Any]:
    """If root profile.yaml exists, copy identity fields onto the original user."""
    if not LEGACY_PROFILE_PATH.exists():
        return raw
    try:
        legacy = _load_yaml(LEGACY_PROFILE_PATH)
    except Exception:
        return raw
    merged = dict(raw)
    for key in (
        "name",
        "email",
        "email_subject",
        "phone",
        "move_in",
        "message_template",
        "follow_up_template",
        "append_hold_question",
        "about",
        "one_liner",
        "page_title",
        "deadline",
    ):
        if legacy.get(key) not in (None, ""):
            merged[key] = legacy[key]
    if legacy.get("budget") and not merged.get("budget"):
        merged["budget"] = legacy["budget"]
    return merged


def load_all_users(*, force: bool = False) -> dict[str, dict[str, Any]]:
    """Map user id → raw profile dict."""
    global _users_cache
    if _users_cache is not None and not force:
        return _users_cache

    ensure_profiles()
    users: dict[str, dict[str, Any]] = {}
    for path in sorted(PROFILES_DIR.glob("*.yaml")) + sorted(PROFILES_DIR.glob("*.yml")):
        raw = _load_yaml(path)
        user_id = str(raw.get("id") or path.stem).strip() or path.stem
        user_id = _slug(user_id)
        raw["id"] = user_id
        raw["_path"] = str(path)
        if user_id == ORIGINAL_USER_ID:
            raw = _overlay_legacy_identity(raw)
            raw["id"] = ORIGINAL_USER_ID
        users[user_id] = raw

    if not users:
        users[DEFAULT_USER_ID] = {"id": DEFAULT_USER_ID, "name": "Haneul", "budget": 1500}

    _users_cache = users
    return users


def invalidate_users_cache() -> None:
    global _users_cache
    _users_cache = None


def list_users() -> list[dict[str, Any]]:
    rows = []
    for user_id, raw in load_all_users().items():
        rows.append(user_public_dict(raw))
    rows.sort(key=lambda row: (0 if row["id"] == DEFAULT_USER_ID else 1, row["name"].lower()))
    return rows


def user_public_dict(raw: dict[str, Any]) -> dict[str, Any]:
    user_id = str(raw.get("id") or "")
    name = str(raw.get("name") or user_id).strip() or user_id
    budget = raw.get("budget")
    search = raw.get("search") if isinstance(raw.get("search"), dict) else {}
    if budget is None:
        budget = (search or {}).get("max_rent")
    if budget is None and raw.get("search_preset") == "original":
        budget = 1300
    page_title = str(raw.get("page_title") or "").strip()
    return {
        "id": user_id,
        "name": name,
        "pageTitle": page_title,
        "budget": int(budget) if budget is not None else None,
        "preset": raw.get("search_preset") or "",
    }


def get_user(user_id: str) -> dict[str, Any] | None:
    if not user_id:
        return None
    return load_all_users().get(_slug(user_id))


def read_persisted_user_id() -> str:
    if ACTIVE_USER_FILE.exists():
        value = ACTIVE_USER_FILE.read_text(encoding="utf-8").strip()
        if value and get_user(value) is not None:
            return _slug(value)
    users = load_all_users()
    if DEFAULT_USER_ID in users:
        persist_active_user_id(DEFAULT_USER_ID)
        return DEFAULT_USER_ID
    first = next(iter(users))
    persist_active_user_id(first)
    return first


def persist_active_user_id(user_id: str) -> None:
    ACTIVE_USER_FILE.write_text(_slug(user_id) + "\n", encoding="utf-8")


def current_user_id() -> str:
    request_id = _request_user_id.get()
    if request_id and get_user(request_id) is not None:
        return _slug(request_id)
    return read_persisted_user_id()


def set_active_user_id(user_id: str) -> dict[str, Any]:
    raw = get_user(user_id)
    if raw is None:
        raise KeyError(f"Unknown user: {user_id}")
    persist_active_user_id(raw["id"])
    set_request_user_id(raw["id"])
    return raw


def current_user_raw() -> dict[str, Any]:
    users = load_all_users()
    uid = current_user_id()
    if uid in users:
        return users[uid]
    return next(iter(users.values()))


def current_user_db_path() -> Path:
    env_path = __import__("os").getenv("DB_PATH", "").strip()
    if env_path:
        return Path(env_path)
    uid = current_user_id()
    if uid == ORIGINAL_USER_ID:
        return LEGACY_DB_PATH
    path = DATA_DIR / uid / "listings.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_message_template(name: str, move_in: str, budget: int, phone: str, email: str) -> str:
    intro = name.strip() or "there"
    return (
        f"Hi! I'm interested in your room listing.\n\n"
        f"I'm {intro}. I can move in {move_in}, and my budget is around ${budget}/month.\n"
        f"Phone: {phone}\n"
        f"Email: {email}\n"
    )


def profile_dict(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Identity fields used for outreach / UI titles."""
    data = dict(raw or current_user_raw())
    search = data.get("search") if isinstance(data.get("search"), dict) else {}
    budget = int(data.get("budget") or search.get("max_rent") or 1500)
    name = str(data.get("name") or "").strip()
    move_in = str(data.get("move_in") or search.get("move_in_window_label") or "soon")
    email = str(data.get("email") or "").strip()
    phone = str(data.get("phone") or "").strip()
    template = str(data.get("message_template") or "").strip()
    if not template:
        template = _default_message_template(name, move_in, budget, phone, email)
    return {
        "id": data.get("id"),
        "name": name,
        "email": email,
        "email_subject": str(data.get("email_subject") or "Room Rental Inquiry").strip(),
        "phone": phone,
        "move_in": move_in,
        "budget": budget,
        "message_template": template,
        "follow_up_template": str(data.get("follow_up_template") or "").strip(),
        "append_hold_question": bool(data.get("append_hold_question", True)),
        "about": data.get("about"),
        "one_liner": data.get("one_liner"),
        "page_title": data.get("page_title"),
        "deadline": data.get("deadline") or data.get("page_deadline"),
        "search_preset": data.get("search_preset") or "",
    }


def search_criteria_for(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolved SEARCH_CRITERIA dict for a user (or the active user)."""
    data = dict(raw or current_user_raw())
    if str(data.get("search_preset") or "") == "original":
        from lfr.config import ORIGINAL_SEARCH_CRITERIA

        criteria = dict(ORIGINAL_SEARCH_CRITERIA)
        criteria["require_move_in_window"] = True
        return criteria

    search = data.get("search") if isinstance(data.get("search"), dict) else {}
    budget = int(data.get("budget") or search.get("max_rent") or 1500)
    preferred = list(search.get("neighborhoods_preferred") or data.get("neighborhoods_preferred") or [])
    nearby = list(search.get("neighborhoods_nearby") or data.get("neighborhoods_nearby") or [])
    from lfr.config import neighborhoods_around_named

    around = neighborhoods_around_named(preferred, nearby)
    layouts = list(search.get("room_layouts") or data.get("room_layouts") or [])
    focus_min = int(search.get("price_focus_min") or max(700, budget - 600))
    focus_max = int(search.get("price_focus_max") or budget)
    require_window = bool(search.get("require_move_in_window", False))
    move_in_start = _as_date(search.get("move_in_start"), date.today() if require_window else None)
    move_in_end = _as_date(
        search.get("move_in_end"),
        date(date.today().year + 1, 12, 31) if require_window else None,
    )
    hard_after = _as_date(search.get("move_in_hard_reject_after"), None)

    preferred_label = ", ".join(preferred) if preferred else "San Francisco"
    around_label = ", ".join(around) if around else "adjacent blocks"
    layout_labels = [
        str(item.get("label") or f"{item.get('beds')}r{item.get('baths')}b")
        for item in layouts
        if isinstance(item, dict)
    ]
    layout_note = ", ".join(layout_labels) if layout_labels else "private room"
    others = " Other layouts still OK." if search.get("others_ok", True) else ""

    return {
        "max_rent": budget,
        "price_focus_min": focus_min,
        "price_focus_max": focus_max,
        "price_match_max": int(search.get("price_match_max") or budget),
        "min_acceptable_sqft": int(search.get("min_acceptable_sqft") or 100),
        "nice_to_have_sqft": int(search.get("nice_to_have_sqft") or 150),
        "size_preference_note": search.get("size_preference_note")
        or "Only penalize explicit sqft under 100. 150+ sq ft is a nice-to-have boost.",
        "move_in_start": move_in_start,
        "move_in_end": move_in_end,
        "move_in_hard_reject_after": hard_after,
        "move_in_flex_weeks": int(search.get("move_in_flex_weeks") or 0),
        "require_move_in_window": require_window,
        "use_filter_not_score": bool(search.get("use_filter_not_score", True)),
        "move_in_window": {
            "target": str(search.get("move_in_window_label") or data.get("move_in") or "flexible / available now"),
            "note": (
                "No hard move-in window — available now and unknown dates are OK."
                if not require_window
                else str(search.get("move_in_note") or "")
            ),
        },
        "room_type": search.get("room_type") or "private_bedroom_or_whole_1br_or_share",
        "room_type_note": search.get("room_type_note")
        or (
            f"Prefer {layout_note}.{others} "
            "Reject shared bedroom, SRO/hostel, curtain rooms, office subleases."
        ),
        "room_layouts": layouts,
        "others_ok": bool(search.get("others_ok", True)),
        "scout_apartments": bool(search.get("scout_apartments", True)),
        "current_location": str(search.get("current_location") or (preferred[0] if preferred else "Chinatown")),
        "location": [f"San Francisco — {preferred_label}"],
        "location_note": search.get("location_note")
        or (
            f"Focus: {preferred_label}. Surrounding areas are included automatically "
            f"({around_label}). "
            "Hard-reject Richmond, Sunset/Parkside, Ingleside, Excelsior, East Bay, Daly City, SSF."
        ),
        "neighborhoods_preferred": preferred,
        "neighborhoods_nearby": nearby,
        "neighborhoods_around": around,
        "neighborhoods_penalize": list(
            search.get("neighborhoods_penalize")
            or [
                "Richmond",
                "Sunset",
                "Parkside",
                "Ingleside",
                "Excelsior",
                "Oakland",
                "Emeryville",
                "South San Francisco",
                "Daly City",
            ]
        ),
        "penalize": list(search.get("penalize") or []),
        "wants": search.get("wants")
        or (
            f"Private 1r1b whole unit, or one room in a 2r2b / 3r3b / 3r2b, around {preferred_label}, "
            f"up to ${budget}/month. Other layouts welcome."
        ),
        "transit_priority": search.get("transit_priority")
        or "Bonus for Muni Metro/tram or Caltrain within ~10 min walk.",
    }


def current_user() -> "UserView":
    raw = current_user_raw()
    return UserView(raw)


class UserView:
    """Convenience wrapper around a profile YAML dict."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw

    @property
    def id(self) -> str:
        return str(self.raw.get("id") or DEFAULT_USER_ID)

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or self.id)

    @property
    def search_preset(self) -> str:
        return str(self.raw.get("search_preset") or "")

    @property
    def search_criteria(self) -> dict[str, Any]:
        return search_criteria_for(self.raw)

    @property
    def profile(self) -> dict[str, Any]:
        return profile_dict(self.raw)
