"""Deprecated — notifications archived (lfr.archive.notify)."""

from __future__ import annotations

import sys
from importlib import import_module

# Optional import for anyone still calling notify from old scripts.
try:
    sys.modules[__name__] = import_module("lfr.archive.notify")
except Exception:  # pragma: no cover
    pass
