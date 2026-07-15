"""Backward-compatible CLI shim — implementation: `lfr.sync`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.sync")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `sync`, expose the real module object.
sys.modules[__name__] = _mod
