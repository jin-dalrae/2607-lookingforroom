"""Backward-compatible CLI shim — implementation: `lfr.mail.gmail_draft`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.mail.gmail_draft")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `gmail_draft`, expose the real module object.
sys.modules[__name__] = _mod
