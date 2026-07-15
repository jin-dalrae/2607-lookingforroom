"""Backward-compatible shim — implementation: `lfr.db`."""

from __future__ import annotations

import sys
from importlib import import_module

# Prefer full package surface including private helpers used by legacy imports.
_mod = import_module("lfr.db")
# Also pull score helpers historically re-exported from db.py
from lfr.db.scores import _is_short_term_listing, _listing_with_score  # noqa: E402

sys.modules[__name__] = _mod
# Ensure helpers remain attribute-accessible even if package __init__ omits them.
setattr(_mod, "_is_short_term_listing", _is_short_term_listing)
setattr(_mod, "_listing_with_score", _listing_with_score)
