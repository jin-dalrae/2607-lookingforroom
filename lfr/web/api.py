#!/usr/bin/env python3
"""Local API: create real Gmail drafts and sync application status."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from lfr.apply import create_application, load_profile, standard_apply_message
from lfr.users import (
    current_user_id,
    get_user,
    list_users,
    reset_request_user_id,
    set_active_user_id,
    set_request_user_id,
)
from lfr.channels import default_channel_for_listing, is_facebook_listing
from lfr.db import (
    _listing_with_score,
    get_application_status_map,
    get_listing_by_id,
    init_db,
    mark_application_rejected,
    mark_application_replied,
    mark_application_sent,
    mark_application_skipped,
    set_listing_liked,
    toggle_listing_liked,
    mark_listing_scam,
)
from lfr.mail.gmail_creds import SETUP_INSTRUCTIONS, gmail_configured
from lfr.mail.gmail_draft import create_gmail_draft, format_result

DEFAULT_PORT = 8787
from lfr.paths import PROJECT_ROOT
ROOT = PROJECT_ROOT
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

import threading

_scrape_lock = threading.Lock()
_is_scraping = False
_last_scrape_status = "idle"  # "idle", "running", "success", "failed"
_last_scrape_error = None


CORS_ALLOW_HEADERS = "Content-Type, Authorization, X-LFR-User"


def _apply_cors(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    _apply_cors(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _bind_request_user(handler: BaseHTTPRequestHandler):
    parsed = urlparse(handler.path)
    qs = parse_qs(parsed.query)
    header = (handler.headers.get("X-LFR-User") or "").strip()
    query_user = (qs.get("user") or [""])[0].strip()
    uid = header or query_user
    if uid and get_user(uid) is not None:
        return set_request_user_id(uid)
    return None


def _auto_deploy_after_scrape() -> None:
    flag = os.getenv("SCRAPE_AUTO_DEPLOY", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return
    script = ROOT / "scripts" / "deploy-pages.sh"
    if not script.is_file():
        print("[api] SCRAPE_AUTO_DEPLOY set but deploy-pages.sh missing", file=sys.stderr)
        return
    print("[api] Deploying updated listings to Cloudflare Pages…")
    subprocess.run([str(script)], cwd=ROOT, check=True)


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
        _apply_cors(self)
        self.end_headers()

    def do_GET(self) -> None:
        token = _bind_request_user(self)
        try:
            self._do_GET()
        finally:
            if token is not None:
                reset_request_user_id(token)

    def _do_GET(self) -> None:
        if not _auth_ok(self):
            _json_response(self, 401, {"ok": False, "error": "Unauthorized"})
            return
        path = urlparse(self.path).path
        if path == "/api/health":
            from lfr.find import gemini_configured

            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "gmail": gmail_configured(),
                    "message": "Apply API ready",
                    "user": current_user_id(),
                    "endpoints": [
                        "draft",
                        "sent",
                        "replied",
                        "skip",
                        "like",
                        "delete",
                        "statuses",
                        "scrape",
                        "scrape/status",
                        "scam",
                        "revert",
                        "notes",
                        "toured",
                        "accepted",
                        "users",
                        "queue",
                        "find",
                    ],
                    "findAvailable": gemini_configured(),
                },
            )
            return
        if path == "/api/users":
            self._handle_users()
            return
        if path == "/api/queue":
            self._handle_queue()
            return
        if path == "/api/statuses":
            _json_response(
                self,
                200,
                {"ok": True, "statuses": get_application_status_map()},
            )
            return
        if path == "/api/scrape/status":
            self._handle_scrape_status()
            return
        _json_response(self, 404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        token = _bind_request_user(self)
        try:
            self._do_POST()
        finally:
            if token is not None:
                reset_request_user_id(token)

    def _do_POST(self) -> None:
        if not _auth_ok(self):
            _json_response(self, 401, {"ok": False, "error": "Unauthorized"})
            return

        path = urlparse(self.path).path
        if path == "/api/users/active":
            self._handle_set_active_user()
            return
        draft_match = re.match(r"^/api/draft/([^/]+)$", path)
        sent_match = re.match(r"^/api/sent/([^/]+)$", path)
        replied_match = re.match(r"^/api/replied/([^/]+)$", path)
        skip_match = re.match(r"^/api/skip/([^/]+)$", path)
        like_match = re.match(r"^/api/like/([^/]+)$", path)
        delete_match = re.match(r"^/api/delete/([^/]+)$", path)
        scam_match = re.match(r"^/api/scam/([^/]+)$", path)
        revert_match = re.match(r"^/api/revert/([^/]+)$", path)
        notes_match = re.match(r"^/api/notes/([^/]+)$", path)
        toured_match = re.match(r"^/api/toured/([^/]+)$", path)
        accepted_match = re.match(r"^/api/accepted/([^/]+)$", path)

        if draft_match:
            listing_id = draft_match.group(1)
            self._handle_draft(listing_id)
            return
        if sent_match:
            listing_id = sent_match.group(1)
            self._handle_sent(listing_id)
            return
        if replied_match:
            listing_id = replied_match.group(1)
            self._handle_replied(listing_id)
            return
        if skip_match:
            listing_id = skip_match.group(1)
            self._handle_skip(listing_id)
            return
        if like_match:
            listing_id = like_match.group(1)
            self._handle_like(listing_id)
            return
        if delete_match:
            listing_id = delete_match.group(1)
            self._handle_delete(listing_id)
            return
        if scam_match:
            listing_id = scam_match.group(1)
            self._handle_scam(listing_id)
            return
        if revert_match:
            listing_id = revert_match.group(1)
            self._handle_revert(listing_id)
            return
        if notes_match:
            listing_id = notes_match.group(1)
            self._handle_notes(listing_id)
            return
        if toured_match:
            listing_id = toured_match.group(1)
            self._handle_toured(listing_id)
            return
        if accepted_match:
            listing_id = accepted_match.group(1)
            self._handle_accepted(listing_id)
            return
        if path == "/api/scrape":
            self._handle_scrape()
            return
        if path == "/api/find":
            self._handle_find()
            return
        _json_response(self, 404, {"ok": False, "error": "Not found"})

    def _handle_toured(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return

        from lfr.db.connection import get_connection
        now = _utcnow()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE applications
                SET status = 'toured', toured_at = COALESCE(toured_at, ?), updated_at = ?
                WHERE listing_id = ?
                """,
                (now, now, listing["id"]),
            )
            conn.commit()

        _json_response(
            self,
            200,
            {"ok": True, "status": "toured"},
        )

    def _handle_accepted(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return

        from lfr.db.applications import mark_application_accepted
        app = mark_application_accepted(listing["id"])
        _json_response(
            self,
            200,
            {"ok": True, "status": app["status"] if app else "accepted"},
        )

    def _handle_notes(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return

        body = self._read_json_body()
        notes_text = str(body.get("notes") or "").strip()

        from lfr.db.connection import get_connection
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            existing = conn.execute("SELECT 1 FROM applications WHERE listing_id = ?", (listing["id"],)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE applications SET notes = ?, updated_at = ? WHERE listing_id = ?",
                    (notes_text, now, listing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO applications (listing_id, status, draft_text, notes, created_at, updated_at)
                    VALUES (?, 'draft', '', ?, ?, ?)
                    """,
                    (listing["id"], notes_text, now, now),
                )
            conn.commit()

        _json_response(self, 200, {"ok": True, "notes": notes_text})

    def _handle_scam(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return
        mark_listing_scam(listing["id"])
        _json_response(
            self,
            200,
            {"ok": True, "status": "rejected", "is_scam_likely": True},
        )

    def _handle_revert(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return

        from lfr.db.connection import get_connection
        with get_connection() as conn:
            conn.execute("DELETE FROM applications WHERE listing_id = ?", (listing["id"],))
            conn.execute("UPDATE scores SET is_scam_likely = 0 WHERE listing_id = ?", (listing["id"],))
            conn.commit()

        _json_response(
            self,
            200,
            {"ok": True, "status": "draft", "is_scam_likely": False},
        )

    def _handle_find(self) -> None:
        from lfr.find import find_listings, gemini_configured

        if not gemini_configured():
            _json_response(
                self,
                503,
                {"ok": False, "error": "Gemini API key is not configured on the server"},
            )
            return
        body = self._read_json_body()
        question = str(body.get("question") or body.get("q") or "").strip()
        listings = body.get("listings")
        if not isinstance(listings, list):
            listings = []
        try:
            result = find_listings(question, listings)
        except ValueError as exc:
            _json_response(self, 400, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            _json_response(self, 502, {"ok": False, "error": str(exc)})
            return
        _json_response(
            self,
            200,
            {
                "ok": True,
                "ids": result.get("ids") or [],
                "note": result.get("note") or "",
            },
        )

    def _handle_users(self) -> None:
        users = list_users()
        _json_response(
            self,
            200,
            {
                "ok": True,
                "active": current_user_id(),
                "users": users,
            },
        )

    def _handle_set_active_user(self) -> None:
        body = self._read_json_body()
        user_id = str(body.get("id") or body.get("user") or "").strip()
        if not user_id or get_user(user_id) is None:
            _json_response(self, 400, {"ok": False, "error": "Unknown user"})
            return
        raw = set_active_user_id(user_id)
        try:
            from lfr.pipeline.export import write_queue_data

            write_queue_data(run_backfill=False)
        except Exception as exc:
            print(f"[api] export after user switch failed: {exc}", file=sys.stderr)
        _json_response(
            self,
            200,
            {
                "ok": True,
                "active": raw["id"],
                "users": list_users(),
            },
        )

    def _handle_queue(self) -> None:
        try:
            from lfr.pipeline.export import build_queue_payload

            init_db()
            payload = build_queue_payload()
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "error": str(exc)})
            return
        _json_response(self, 200, {"ok": True, "queue": payload, "user": current_user_id()})

    def _handle_scrape_status(self) -> None:
        global _is_scraping, _last_scrape_status, _last_scrape_error
        _json_response(
            self,
            200,
            {
                "ok": True,
                "is_scraping": _is_scraping,
                "status": _last_scrape_status,
                "error": _last_scrape_error,
            },
        )

    def _handle_scrape(self) -> None:
        global _is_scraping, _last_scrape_status, _last_scrape_error
        scrape_user = current_user_id()
        with _scrape_lock:
            if _is_scraping:
                _json_response(self, 400, {"ok": False, "error": "Scrape already in progress"})
                return
            _is_scraping = True
            _last_scrape_status = "running"
            _last_scrape_error = None

        def worker() -> None:
            global _is_scraping, _last_scrape_status, _last_scrape_error
            token = set_request_user_id(scrape_user)
            try:
                from lfr.run import run_pipeline
                from lfr.pipeline.export import write_queue_data

                print(f"[api] Background scrape started for user={scrape_user}…")
                run_pipeline()
                write_queue_data()
                _auto_deploy_after_scrape()
                print("[api] Background scrape finished and queue exported successfully!")
                _last_scrape_status = "success"
            except Exception as exc:
                print(f"[api] Background scrape error: {exc}", file=sys.stderr)
                _last_scrape_status = "failed"
                _last_scrape_error = str(exc)
            finally:
                reset_request_user_id(token)
                _is_scraping = False

        t = threading.Thread(target=worker, name="ScrapeWorker")
        t.daemon = True
        t.start()

        _json_response(self, 200, {"ok": True, "message": "Scrape started"})

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

    def _handle_like(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        liked_raw = self._read_json_body().get("liked")
        if liked_raw is None:
            liked = toggle_listing_liked(listing_id)
        else:
            liked = set_listing_liked(listing_id, bool(liked_raw))
        if liked is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return
        _json_response(self, 200, {"ok": True, "liked": liked})

    def _handle_delete(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return
        app = mark_application_rejected(listing["id"])
        _json_response(
            self,
            200,
            {"ok": True, "status": app["status"] if app else "rejected"},
        )

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            raw = self.rfile.read(length)
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _handle_replied(self, listing_id: str) -> None:
        if not ID_RE.match(listing_id):
            _json_response(self, 400, {"ok": False, "error": "Invalid listing id"})
            return
        init_db()
        listing = _listing_or_404(listing_id)
        if listing is None:
            _json_response(self, 404, {"ok": False, "error": "Listing not found"})
            return
        app = mark_application_replied(listing["id"])
        _json_response(
            self,
            200,
            {"ok": True, "status": app["status"] if app else "replied"},
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
    print("  POST /api/replied/<listing_id>")
    print("  POST /api/skip/<listing_id>")
    print("  POST /api/like/<listing_id>")
    print("  POST /api/delete/<listing_id>")
    if not gmail_configured():
        print("  warning: Gmail not configured — email drafts will fail", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())