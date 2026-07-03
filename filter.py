#!/usr/bin/env python3
"""Gemini-powered batch scorer for room listings (compat shim)."""

from lfr.score import apply_results, run, score_batch
from lfr.score.heuristics import _heuristic_score

__all__ = [
    "apply_results",
    "run",
    "score_batch",
    "_heuristic_score",
]

if __name__ == "__main__":
    from lfr.score.batch import main

    raise SystemExit(main())