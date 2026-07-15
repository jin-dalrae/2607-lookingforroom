"""Backward-compatible shim — implementation: `lfr.channels`."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("lfr.channels")
