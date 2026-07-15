"""Backward-compatible CLI shim — implementation: `lfr.apply`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.apply")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `apply`, expose the real module object.
sys.modules[__name__] = _mod
