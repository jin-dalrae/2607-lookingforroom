"""Backward-compatible CLI shim — implementation: `lfr.mail.mail_monitor`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.mail.mail_monitor")

if __name__ == "__main__":
    raise SystemExit(_mod.main())

# When imported as `mail_monitor`, expose the real module object.
sys.modules[__name__] = _mod
