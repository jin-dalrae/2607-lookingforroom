"""Playwright session helpers for Facebook Marketplace (local login only)."""

from __future__ import annotations

import sys
from pathlib import Path

STATE_PATH = Path(__file__).parent / "facebook_state.json"


def session_configured() -> bool:
    return STATE_PATH.is_file() and STATE_PATH.stat().st_size > 100


def state_path() -> Path:
    return STATE_PATH


def login_instructions() -> str:
    return """
Facebook login (one-time, on your Mac — never share your password in chat):

  1. pip install playwright && playwright install chromium
  2. python scout_facebook.py login
  3. Log in in the browser window that opens
  4. When you see your Facebook feed, return here and press Enter
  5. Session saved to facebook_state.json (gitignored)

Then poll Marketplace:
  python scout_facebook.py poll
  python scout_facebook.py ingest "https://www.facebook.com/marketplace/item/..."

Paste a listing URL into apply / Gmail draft:
  python apply.py "https://www.facebook.com/marketplace/item/..."
""".strip()


def run_interactive_login() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    print("Opening Chromium — log into Facebook in the browser window.")
    print("When your feed or Marketplace loads, come back here and press Enter.\n")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        try:
            input("Press Enter after you are logged in… ")
        except EOFError:
            print("Non-interactive shell — waiting 120s for manual login…", file=sys.stderr)
            page.wait_for_timeout(120_000)
        context.storage_state(path=str(STATE_PATH))
        browser.close()

    print(f"Saved session to {STATE_PATH}")