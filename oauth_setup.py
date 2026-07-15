"""Backward-compatible CLI shim — implementation: `lfr.mail.oauth_setup`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.mail.oauth_setup")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `oauth_setup`, expose the real module object.
sys.modules[__name__] = _mod
