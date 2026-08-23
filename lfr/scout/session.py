"""Playwright session helpers for Facebook Marketplace (local login only)."""

from __future__ import annotations

import sys
from pathlib import Path

from lfr.paths import PROJECT_ROOT
STATE_PATH = PROJECT_ROOT / "facebook_state.json"


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


def _logged_in(context, page) -> bool:
    try:
        cookies = context.cookies()
    except Exception:
        cookies = []
    if not any(cookie.get("name") == "c_user" and cookie.get("value") for cookie in cookies):
        return False
    url = (page.url or "").lower()
    if "login" in url or "checkpoint" in url:
        return False
    return True


def run_interactive_login() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    print("Opening Chromium — log into Facebook in the browser window.")
    print("2FA / checkpoint is OK; wait until your feed or Marketplace is visible.\n")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")

        deadline = __import__("time").time() + 600
        logged_in = False
        while __import__("time").time() < deadline:
            if _logged_in(context, page):
                logged_in = True
                break
            remaining = int(deadline - __import__("time").time())
            print(f"Waiting for Facebook login… ({remaining}s left)", flush=True)
            page.wait_for_timeout(3000)

        if not logged_in:
            browser.close()
            raise RuntimeError(
                "Facebook login did not finish in 10 minutes. "
                "Run: python scout_facebook.py login"
            )

        page.wait_for_timeout(2000)
        context.storage_state(path=str(STATE_PATH))
        browser.close()

    print(f"Saved session to {STATE_PATH}")