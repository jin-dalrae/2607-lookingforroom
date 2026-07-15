"""Backward-compatible CLI shim — implementation: `lfr.scout.zillow`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.scout.zillow")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `scout_zillow`, expose the real module object.
sys.modules[__name__] = _mod
