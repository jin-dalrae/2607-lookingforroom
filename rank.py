"""Backward-compatible CLI shim — implementation: `lfr.rank`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.rank")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `rank`, expose the real module object.
sys.modules[__name__] = _mod
