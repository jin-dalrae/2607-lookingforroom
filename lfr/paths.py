"""Project filesystem roots (repo root, not package dir)."""

from __future__ import annotations

from pathlib import Path

# lfr/paths.py → repo root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
