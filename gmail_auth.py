#!/usr/bin/env python3
"""Shared Gmail OAuth2 helpers for mail_monitor.py and send_mail.py.

Reads credentials from credentials.json (GCP download) OR .env client id/secret.
Token is stored in gmail_token.json (gitignored).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)

TOKEN_FILENAME = "gmail_token.json"
PENDING_FILENAME = "gmail_oauth_pending.json"
CREDENTIALS_FILENAME = "credentials.json"
PROJECT_DIR = Path(__file__).resolve().parent
TOKEN_PATH = PROJECT_DIR / TOKEN_FILENAME
PENDING_PATH = PROJECT_DIR / PENDING_FILENAME
CREDENTIALS_PATH = PROJECT_DIR / CREDENTIALS_FILENAME

# Must match a URI registered in GCP Console → OAuth client → Authorized redirect URIs
DEFAULT_REDIRECT_URI = "http://localhost:8080/"


def _client_id() -> str:
    return os.getenv("GMAIL_OAUTH_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("GMAIL_OAUTH_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.getenv("GMAIL_OAUTH_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()


def oauth_configured() -> bool:
    if CREDENTIALS_PATH.is_file():
        return True
    return bool(_client_id() and _client_secret())


def _client_config() -> dict[str, Any]:
    """Build OAuth client config from .env (Desktop app shape)."""
    uri = redirect_uri()
    return {
        "installed": {
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [uri, "http://localhost", "http://127.0.0.1:8080/"],
        }
    }


def _make_flow():
    """Create OAuth flow from credentials.json or .env."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    uri = redirect_uri()
    if CREDENTIALS_PATH.is_file():
        return InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH),
            SCOPES,
            redirect_uri=uri,
        )
    return InstalledAppFlow.from_client_config(
        _client_config(),
        SCOPES,
        redirect_uri=uri,
    )


def _load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not TOKEN_PATH.is_file():
        return None

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    return creds


def _save_credentials(creds) -> None:
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")


def token_valid() -> bool:
    creds = _load_credentials()
    if creds is None:
        return False
    return bool(creds.valid or creds.refresh_token)


def get_gmail_service():
    from googleapiclient.discovery import build

    creds = _load_credentials()
    if creds is None:
        raise RuntimeError("Gmail OAuth token missing. Run: python oauth_setup.py")
    if not creds.valid:
        if creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
            _save_credentials(creds)
        else:
            raise RuntimeError(
                "Gmail OAuth token expired. Run: python oauth_setup.py"
            )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _save_pending(flow) -> None:
    verifier = getattr(flow, "code_verifier", None)
    if not verifier and hasattr(flow, "oauth2session"):
        verifier = getattr(flow.oauth2session, "code_verifier", None)
    payload = {
        "code_verifier": verifier,
        "redirect_uri": redirect_uri(),
    }
    PENDING_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _load_pending() -> dict[str, Any]:
    if not PENDING_PATH.is_file():
        return {}
    try:
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def print_auth_url() -> str:
    flow = _make_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _save_pending(flow)
    return auth_url


def complete_oauth_redirect(redirect_response: str) -> None:
    pending = _load_pending()
    flow = _make_flow()
    uri = pending.get("redirect_uri") or redirect_uri()
    flow.redirect_uri = uri

    verifier = pending.get("code_verifier")
    if verifier:
        flow.oauth2session.code_verifier = verifier

    text = redirect_response.strip()
    if text.startswith("http"):
        flow.fetch_token(authorization_response=text)
    else:
        flow.fetch_token(code=text)

    _save_credentials(flow.credentials)
    if PENDING_PATH.is_file():
        PENDING_PATH.unlink()
    print(f"Saved OAuth token to {TOKEN_PATH}")


def run_oauth_flow(*, headless: bool = False) -> None:
    if not oauth_configured():
        raise RuntimeError(
            "OAuth not configured. Set .env client id/secret or add credentials.json"
        )

    flow = _make_flow()
    uri = redirect_uri()

    if headless:
        auth_url = print_auth_url()
        print("Open this URL (incognito with your Google Account):\n")
        print(auth_url)
        print(f"\nRedirect URI: {uri}")
        print("\nAfter Allow, paste the full localhost URL or code:")
        response = input("Paste here: ").strip()
        complete_oauth_redirect(response)
        return

    # Fixed port 8080 — must be registered in GCP redirect URIs
    creds = flow.run_local_server(
        port=8080,
        redirect_uri_trailing_slash=False,
        prompt="consent",
        open_browser=True,
    )
    _save_credentials(creds)
    if PENDING_PATH.is_file():
        PENDING_PATH.unlink()
    print(f"Saved OAuth token to {TOKEN_PATH}")


def auth_status() -> dict[str, Any]:
    return {
        "oauth_configured": oauth_configured(),
        "token_valid": token_valid(),
        "token_path": str(TOKEN_PATH),
        "credentials_json": CREDENTIALS_PATH.is_file(),
        "redirect_uri": redirect_uri(),
        "client_id_set": bool(_client_id()),
        "client_secret_set": bool(_client_secret()),
    }


GCP_REDIRECT_FIX = """
redirect_uri_mismatch — fix in GCP Console:

1. Open https://console.cloud.google.com/apis/credentials
2. Click your OAuth 2.0 Client ID
3. Under "Authorized redirect URIs" ADD these (if missing):
     http://localhost:8080
     http://localhost:8080/
     http://localhost
     http://127.0.0.1:8080
4. Save. Wait 1–2 minutes.
5. Re-run: python oauth_setup.py

Tip: Download JSON → save as credentials.json in this folder (gitignored).
     Application type should be "Desktop app" OR "Web" with URIs above.
""".strip()