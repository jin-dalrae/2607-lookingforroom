"""Backward-compatible shim — implementation: `lfr.archive.communication_page`."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("lfr.archive.communication_page")
