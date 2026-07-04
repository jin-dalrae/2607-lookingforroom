"""Move-in date extraction, classification, and score adjustments."""

from __future__ import annotations

from datetime import date
from typing import Any

from config import MOVE_IN_SCORING

from lfr.listings.move_in import is_utility_fraction, move_in_after_cutoff_hit
from lfr.score.criteria import (
    MOVE_IN_FIT_VALUES,
    MOVE_IN_REFERENCE_TODAY,
    MOVE_IN_TARGET_END,
    MOVE_IN_TARGET_START,
    MOVE_IN_WINDOW_END,
    MOVE_IN_WINDOW_START,
    _MONTH_NAMES,
    _MOVE_IN_AUGUST_RE,
    _MOVE_IN_AVAILABLE_MONTH_RE,
    _MOVE_IN_FLEXIBLE_RE,
    _MOVE_IN_IMMEDIATE_RE,
    _MOVE_IN_LATE_JULY_RE,
    _MOVE_IN_MONTH_DAY_RE,
    _MOVE_IN_QUALIFIER_RE,
    _MOVE_IN_SLASH_DATE_RE,
)

def _month_token_to_number(token: str) -> int | None:
    return _MONTH_NAMES.get(token.lower().strip())


def _safe_move_in_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _infer_move_in_year(month: int, explicit_year: int | None = None) -> int:
    if explicit_year is not None:
        if explicit_year < 100:
            return 2000 + explicit_year
        return explicit_year
    year = MOVE_IN_REFERENCE_TODAY.year
    if month < MOVE_IN_REFERENCE_TODAY.month - 1:
        year += 1
    return year


def _qualifier_to_day(qualifier: str, *, month: int | None = None) -> int:
    q = qualifier.lower()
    if q == "early":
        return 5
    if q == "mid":
        return 12
    if month == 8:
        return MOVE_IN_TARGET_END.day
    return 25


def _extract_move_in_candidates(
    text: str,
    move_in_date_field: str | None = None,
) -> list[tuple[str, date | None, str]]:
    """Return (signal_text, parsed_date_or_none, signal_kind) candidates."""
    candidates: list[tuple[str, date | None, str]] = []
    combined = text
    if move_in_date_field:
        combined = f"{combined} {str(move_in_date_field).lower()}"

    for match in _MOVE_IN_IMMEDIATE_RE.finditer(combined):
        candidates.append((match.group(0).strip().lower(), None, "immediate"))

    if _MOVE_IN_FLEXIBLE_RE.search(combined):
        candidates.append(("flexible move-in", None, "flexible"))

    for match in _MOVE_IN_AVAILABLE_MONTH_RE.finditer(combined):
        month = _month_token_to_number(match.group(1))
        day = int(match.group(2))
        if month is None:
            continue
        year = _infer_move_in_year(month)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"available {match.group(1)} {day}"
        candidates.append((signal, parsed, "date"))

    for match in _MOVE_IN_MONTH_DAY_RE.finditer(combined):
        month = _month_token_to_number(match.group(1))
        day = int(match.group(2))
        if month is None:
            continue
        explicit_year = int(match.group(3)) if match.group(3) else None
        year = _infer_move_in_year(month, explicit_year)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"{match.group(1)} {day}"
        candidates.append((signal, parsed, "date"))

    from lfr.listings.move_in import is_utility_fraction

    for match in _MOVE_IN_SLASH_DATE_RE.finditer(combined):
        if is_utility_fraction(combined, match):
            continue
        month = int(match.group(1))
        day = int(match.group(2))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        explicit_year = int(match.group(3)) if match.group(3) else None
        year = _infer_move_in_year(month, explicit_year)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"{month}/{day}"
        candidates.append((signal, parsed, "date"))

    for match in _MOVE_IN_QUALIFIER_RE.finditer(combined):
        month = _month_token_to_number(match.group(2))
        if month is None:
            continue
        day = _qualifier_to_day(match.group(1), month=month)
        year = _infer_move_in_year(month)
        parsed = _safe_move_in_date(year, month, day)
        signal = f"{match.group(1).lower()}-{match.group(2).lower()}"
        candidates.append((signal, parsed, "qualifier"))

    if _MOVE_IN_LATE_JULY_RE.search(combined):
        year = _infer_move_in_year(7)
        candidates.append(("late july", date(year, 7, 25), "qualifier"))

    if _MOVE_IN_AUGUST_RE.search(combined):
        candidates.append(
            ("available in august", date(_infer_move_in_year(8), 8, 10), "qualifier")
        )

    return candidates


def _classify_move_in_date(
    parsed_date: date | None,
    *,
    signal_kind: str,
    signal_text: str = "",
) -> str:
    """Classify move-in vs hard window August 1 – Aug 18, 2026."""
    if parsed_date is None:
        if signal_kind == "immediate":
            return "risky"
        if signal_kind == "flexible":
            return "unknown"
        return "unknown"

    if parsed_date > MOVE_IN_WINDOW_END:
        return "too_late"

    if parsed_date < MOVE_IN_WINDOW_START:
        return "too_early"

    if MOVE_IN_WINDOW_START <= parsed_date <= MOVE_IN_WINDOW_END:
        return "ideal"

    return "unknown"


def _landlord_wait_likely(move_in_fit: str, *, has_immediate_signal: bool) -> bool | None:
    if move_in_fit == "ideal":
        return True
    if move_in_fit == "maybe":
        return None
    if move_in_fit == "risky":
        if has_immediate_signal:
            return False
        return False
    if move_in_fit == "too_late":
        return False
    return None


def _analyze_move_in(
    text: str,
    move_in_date_field: str | None = None,
) -> dict[str, Any]:
    """Parse move-in signals from listing text and classify fit vs user window."""
    from lfr.listings.move_in import move_in_after_cutoff_hit

    combined = text
    if move_in_date_field:
        combined = f"{combined} {str(move_in_date_field).lower()}"
    hit, signal = move_in_after_cutoff_hit(combined)
    if hit:
        return {
            "move_in_signal": signal,
            "move_in_fit": "too_late",
            "landlord_wait_likely": False,
            "parsed_date": None,
        }

    candidates = _extract_move_in_candidates(text, move_in_date_field)
    has_immediate = any(kind == "immediate" for _, _, kind in candidates)
    has_flexible = any(kind == "flexible" for _, _, kind in candidates)

    move_in_signal: str | None = None
    parsed_date: date | None = None
    move_in_fit = "unknown"

    date_candidates = [(s, d, k) for s, d, k in candidates if k in ("date", "qualifier")]
    immediate_candidates = [(s, d, k) for s, d, k in candidates if k == "immediate"]

    if date_candidates:
        best_signal, best_date, best_kind = date_candidates[0]
        best_fit = _classify_move_in_date(
            best_date, signal_kind=best_kind, signal_text=best_signal
        )
        for signal, parsed, kind in date_candidates[1:]:
            fit = _classify_move_in_date(
                parsed, signal_kind=kind, signal_text=signal
            )
            priority = {
                "ideal": 0,
                "maybe": 1,
                "unknown": 2,
                "risky": 3,
                "too_early": 4,
                "too_late": 5,
            }
            if priority.get(fit, 5) < priority.get(best_fit, 5):
                best_signal, best_date, best_fit = signal, parsed, fit
        move_in_signal = best_signal
        parsed_date = best_date
        move_in_fit = best_fit
        if has_immediate and best_fit in ("ideal", "maybe", "unknown"):
            move_in_fit = "risky"
            move_in_signal = immediate_candidates[0][0] if immediate_candidates else "available now"
    elif immediate_candidates:
        move_in_signal = immediate_candidates[0][0]
        move_in_fit = "risky"
    elif has_flexible:
        move_in_signal = "flexible move-in"
        move_in_fit = "ideal"

    landlord_wait = _landlord_wait_likely(move_in_fit, has_immediate_signal=has_immediate)

    return {
        "move_in_signal": move_in_signal,
        "move_in_fit": move_in_fit,
        "landlord_wait_likely": landlord_wait,
        "parsed_date": parsed_date,
    }


def _move_in_fit_note(move_in_fit: str, move_in_signal: str | None) -> str | None:
    signal = move_in_signal or "unspecified"
    notes = {
        "ideal": f"move-in {signal} — Aug 1–18 OK",
        "maybe": f"move-in {signal} — outside window",
        "risky": "available now — excluded (need Aug 1–18)",
        "too_early": f"move-in {signal} — before August",
        "too_late": f"move-in {signal} — after Aug 18 / available after Aug 19+",
        "unknown": "move-in unknown — excluded",
    }
    return notes.get(move_in_fit)


def _apply_move_in_scoring(
    *,
    score: int,
    flags: list[str],
    parts: list[str],
    move_in_info: dict[str, Any],
) -> tuple[int, dict[str, Any], list[str], list[str]]:
    """Adjust score/reasoning for move-in fit."""
    move_in_fit = str(move_in_info.get("move_in_fit") or "unknown")
    move_in_signal = move_in_info.get("move_in_signal")

    adjustments = MOVE_IN_SCORING["adjustments"]
    score += adjustments.get(move_in_fit, 0)

    note = _move_in_fit_note(move_in_fit, move_in_signal)
    if note:
        parts.append(note)
    if move_in_fit != "unknown":
        flags.append(f"move_in_{move_in_fit}")
    if move_in_fit == "too_late":
        flags.append("move_in_late_reject")

    return score, move_in_info, flags, parts
