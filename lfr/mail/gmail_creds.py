"""Gmail login via email + password (Google App Password for IMAP/SMTP)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

SETUP_INSTRUCTIONS = """
Gmail not configured. App Password is required (not your normal Gmail login).

Add to .env:

  GMAIL_ADDRESS=your-email@gmail.com
  GMAIL_PASSWORD=your-16-char-app-password

How to create GMAIL_PASSWORD:
  1. Enable 2-Step Verification: https://myaccount.google.com/security
  2. App passwords: https://myaccount.google.com/apppasswords
     (Mail → name it "Looking for Room" → copy 16-character code)
  3. Paste as GMAIL_PASSWORD (spaces OK). Legacy key GMAIL_APP_PASSWORD also works.

Verify: python -c "from lfr.mail.gmail_creds import gmail_configured; print(gmail_configured())"
Then: python mail_monitor.py
""".strip()


def gmail_address() -> str:
    addr = os.getenv("GMAIL_ADDRESS", "").strip()
    if addr:
        return addr
    from lfr.paths import PROJECT_ROOT
    profile_path = PROJECT_ROOT / "profile.yaml"
    try:
        with profile_path.open(encoding="utf-8") as fh:
            profile = yaml.safe_load(fh) or {}
        return str(profile.get("email", "")).strip()
    except OSError:
        return ""


def gmail_password() -> str:
    """App password (GMAIL_PASSWORD or legacy GMAIL_APP_PASSWORD)."""
    for key in ("GMAIL_PASSWORD", "GMAIL_APP_PASSWORD"):
        value = os.getenv(key, "").strip().replace(" ", "")
        if value:
            return value
    return ""


def gmail_configured() -> bool:
    return bool(gmail_address() and gmail_password())


def auth_mode() -> str:
    return "imap" if gmail_configured() else "none"