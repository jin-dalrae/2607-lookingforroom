"""Pipeline: hard filters, queue export."""

from lfr.pipeline.match import (
    listing_matches_criteria,
    price_in_focus_band,
    price_within_budget,
    sort_matches,
)

__all__ = [
    "build_queue_payload",
    "listing_matches_criteria",
    "price_in_focus_band",
    "price_within_budget",
    "sort_matches",
    "write_queue_data",
]


def __getattr__(name: str):
    if name in ("build_queue_payload", "write_queue_data"):
        from lfr.pipeline import export

        return getattr(export, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")