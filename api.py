"""Backward-compatible CLI shim — implementation: `lfr.web.api`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.web.api")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `api`, expose the real module object.
sys.modules[__name__] = _mod
