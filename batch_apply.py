"""Backward-compatible shim — implementation: `lfr.archive.batch_apply`."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("lfr.archive.batch_apply")
