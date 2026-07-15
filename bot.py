"""Deprecated — Telegram bot archived (lfr.archive.bot). Not required for the apply queue."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "Telegram bot is archived and no longer part of the default setup.\n"
        "Use the web queue at http://127.0.0.1:8765/ instead.\n"
        "(Implementation kept at lfr/archive/bot.py if you need it.)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
