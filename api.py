#!/usr/bin/env python3
"""Local API: create real Gmail drafts and sync application status."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from apply import create_application, load_profile, standard_apply_message
from channels import default_channel_for_listing, is_facebook_listing
from db import (
    _listing_with_score,
    get_listing_by_id,
    init_db,
    mark_application_sent,
    mark_application_skipped,
)
from gmail_creds import SETUP_INSTRUCTIONS, gmail_configured
from gmail_draft import create_gmail_draft, format_result

DEFAULT_PORT = 8787
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.end_headers()
    handler.wfile.write(body)


def _auth_ok(handler: BaseHTTPRequestHandler) -> bool:
    token = os.getenv("APPLY_API_TOKEN", "").strip()
    if not token:
        return True
    header = handler.headers.get("Authorization", "")
    if header == f"Bearer {token}":
        return True
    return False


def _listing_or_404(listing_id: str) -> dict[str, Any] | None:
    listing = _listing_with_score(listing_id)
    if listing is not None:
        return listing
    row = get_listing_by_id(listing_id)
    if row is None:
        return None
    return _listing_with_score(row["id"]) or dict(row)


class ApplyAPIHandler(BaseHTTPRequestHandler):
    server_version = "ApplyAPI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[api] {self.address_string()} {fmt % args}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        if not _auth_ok(self):
            _json_response(self, 401, {"ok": False, "error": "Unauthorized"})
            return
        path = urlparse(self.path).path
        if path == "/api/health":
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "gmail": gmail_configured(),
                    "message": "Apply API ready",
                },
            )
            return
        _json_response(self, 404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        if not _auth_ok(self):
            _json_response(self, 401, {"ok": False, "error": "Unauthorized"})
            return

        path = urlparse(self.path).path
        draft_match = re.match(r"^/api/draft/([^/]+)$", path)
        sent_match = re.match(r"^/api/sent/([^/]+)$", path)
        skip_match = re.match(r"^/api/skip/([^/]+)$", path)

        if draft_match:
            listing_id = draft_match.group(1)
            self._handle_draft(listing_id)
            return
        if sent_match:
            listing_id = sent_match.group(1)
            self._handle_sent(listing_id)
            return
        if skip_match:
            listing_id = skip_match.group(1)
            self._handle_skip(listing_id)
            return
        _json_response(self, 404, {"ok": False, "error": "Not found"})

    def _handle_draft(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return

        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return

        profile = load_profile()
        channel = default_channel_for_listing(listing)
        message = standard_apply_message(profile, listing.get("url") or "")

        if is_facebook_listing(listing):
            create_application(listing["id"], profile)
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "mode": "facebook",
                    "channel": channel,
                    "message": message,
                    "url": listing.get("url"),
                    "hint": "Open listing → Message seller → paste the message.",
                },
            )
            return

        if not gmail_configured():
            _json_response(
                self,
                503,
                {
                    "ok": False,
                    "error": "Gmail not configured",
                    "setup": SETUP_INSTRUCTIONS,
                    "fallback": "gmailComposeUrl",
                },
            )
            return

        try:
            create_application(listing["id"], profile)
            summary = create_gmail_draft(listing, profile)
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "mode": "gmail_draft",
                    "channel": channel,
                    "summary": summary,
                    "text": format_result(summary, listing),
                },
            )
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "error": str(exc)})

    def _handle_skip(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return
        app = mark_application_skipped(listing["id"])
        _json_response(
            self,
            200,
            {"ok": True, "status": app["status"] if app else "skipped"},
        )

    def _handle_sent(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return
        channel = default_channel_for_listing(listing)
        app = mark_application_sent(listing["id"], channel=channel)
        _json_response(
            self,
            200,
            {"ok": True, "status": app["status"] if app else "sent", "channel": channel},
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local apply API (Gmail drafts)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), ApplyAPIHandler)
    print(f"Apply API http://{args.host}:{args.port}")
    print("  GET  /api/health")
    print("  POST /api/draft/<listing_id>")
    print("  POST /api/sent/<listing_id>")
    print("  POST /api/skip/<listing_id>")
    if not gmail_configured():
        print("  warning: Gmail not configured — email drafts will fail", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())