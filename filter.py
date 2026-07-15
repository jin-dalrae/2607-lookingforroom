"""Backward-compatible CLI shim — implementation: `lfr.score`."""

from __future__ import annotations

import sys
from importlib import import_module

_mod = import_module("lfr.score")
# Historically also re-exported a private heuristic helper.
from lfr.score.heuristics import _heuristic_score  # noqa: E402
setattr(_mod, "_heuristic_score", _heuristic_score)

if __name__ == "__main__":
    from lfr.score.batch import main
    raise SystemExit(main())

sys.modules[__name__] = _mod
