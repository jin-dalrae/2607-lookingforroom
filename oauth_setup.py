#!/usr/bin/env python3
"""One-time Gmail OAuth2 setup — saves gmail_token.json.

Usage:
    python oauth_setup.py              # opens browser (default)
    python oauth_setup.py --headless   # prints URL, paste auth code

Requires in .env:
    GMAIL_OAUTH_CLIENT_ID
    GMAIL_OAUTH_CLIENT_SECRET   (from GCP Console → Credentials)
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

import gmail_auth

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time Gmail OAuth2 consent (saves gmail_token.json)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Print authorization URL instead of opening a browser",
    )
    parser.add_argument(
        "--url",
        action="store_true",
        help="Print auth URL only (saves PKCE state for --redirect)",
    )
    parser.add_argument(
        "--redirect",
        metavar="URL_OR_CODE",
        help="Complete OAuth with redirect URL or code from browser",
    )
    args = parser.parse_args()

    if not gmail_auth.oauth_configured():
        print(
            "OAuth client not fully configured.\n\n"
            "1. Enable Gmail API in GCP project 267981036962\n"
            "2. Configure OAuth consent screen\n"
            "3. Create OAuth 2.0 Client (Desktop app)\n"
            "4. Add to .env:\n"
            "   GMAIL_OAUTH_CLIENT_ID=...\n"
            "   GMAIL_OAUTH_CLIENT_SECRET=...   # from Credentials page\n",
            file=sys.stderr,
        )
        return 1

    try:
        if args.redirect:
            gmail_auth.complete_oauth_redirect(args.redirect)
        elif args.url:
            print(gmail_auth.print_auth_url())
            print(f"\nRedirect URI: {gmail_auth.redirect_uri()}")
            print("\nSign in as dalrae.jin.work@gmail.com, then run:")
            print('  python oauth_setup.py --redirect "PASTE_REDIRECT_URL"')
        else:
            gmail_auth.run_oauth_flow(headless=args.headless)
    except Exception as exc:
        err = str(exc)
        print(f"OAuth setup failed: {exc}", file=sys.stderr)
        if "redirect_uri_mismatch" in err or "redirect_uri" in err.lower():
            print(f"\n{gmail_auth.GCP_REDIRECT_FIX}", file=sys.stderr)
        return 1

    print("\nGmail OAuth ready. mail_monitor.py and send_mail.py will use the API.")
    print("Verify: python -c \"import gmail_auth; print(gmail_auth.auth_status())\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())