"""Looking For Room application package.

Layout
------
- ``lfr.scout``   — Craigslist / Facebook / Zillow fetchers
- ``lfr.mail``    — optional Gmail OAuth, drafts, send, inbox monitor
- ``lfr.web``     — local apply API
- ``lfr.db``      — SQLite access
- ``lfr.listings``— field parsers (address, move-in, dates, …)
- ``lfr.pipeline``— match rules + queue export
- ``lfr.score``   — local heuristic scoring (optional Gemini)
- ``lfr.archive`` — deprecated extras (Telegram bot, etc.)

Root-level ``*.py`` files are thin shims so ``python run.py`` and
``from config import …`` keep working without changing call sites.
"""