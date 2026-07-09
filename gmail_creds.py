"""Gmail login via email + password (Google App Password for IMAP/SMTP)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

SETUP_INSTRUCTIONS = """
Gmail not configured. Add to .env:

  GMAIL_ADDRESS=your-email@gmail.com
  GMAIL_PASSWORD=your-16-char-app-password

How to get the password (NOT your normal Gmail login):
  1. Enable 2-Step Verification: https://myaccount.google.com/security
  2. Create App Password: https://myaccount.google.com/apppasswords
     (Mail → name it "Housing bot" → copy 16-character code)
  3. Paste that code as GMAIL_PASSWORD in .env (spaces OK)

Then:
  python mail_monitor.py          # check inbox for landlord replies
  python mail_monitor.py --loop 300
""".strip()


def gmail_address() -> str:
    addr = os.getenv("GMAIL_ADDRESS", "").strip()
    if addr:
        return addr
    profile_path = Path(__file__).parent / "profile.yaml"
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