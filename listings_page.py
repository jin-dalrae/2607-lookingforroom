#!/usr/bin/env python3
"""Generate site/index.html — ranked listing list with Gmail draft buttons."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from apply import load_profile, standard_apply_message
from db import _is_unapplied_listing, get_ranked_listings, init_db
from send_mail import extract_listing_email

OUTPUT_PATH = Path(__file__).parent / "site" / "index.html"
DEFAULT_LIMIT = 50


def _gmail_compose_url(*, to: str, subject: str, body: str) -> str:
    params = f"view=cm&fs=1&su={quote(subject)}&body={quote(body)}"
    if to:
        params += f"&to={quote(to)}"
    return f"https://mail.google.com/mail/?{params}"


def _listing_rows(limit: int) -> list[dict[str, Any]]:
    ranked = get_ranked_listings(limit=limit, exclude_scams=True)
    unapplied = [row for row in ranked if _is_unapplied_listing(row["id"])]
    applied_ids = {row["id"] for row in ranked} - {row["id"] for row in unapplied}
    applied = [row for row in ranked if row["id"] in applied_ids]
    return unapplied + applied


def _serialize_listings(rows: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    subject = (profile.get("email_subject") or "Room Rental Inquiry by Aug 18").strip()
    payload: list[dict[str, Any]] = []
    for row in rows:
        url = row.get("url") or ""
        to_addr = extract_listing_email(row) or ""
        body = standard_apply_message(profile, url)
        payload.append(
            {
                "id": row["id"],
                "title": row.get("title") or "Untitled",
                "price": row.get("price"),
                "neighborhood": row.get("neighborhood") or "Unknown",
                "url": url,
                "source": row.get("source") or "craigslist",
                "unapplied": _is_unapplied_listing(row["id"]),
                "to": to_addr,
                "gmailUrl": _gmail_compose_url(to=to_addr, subject=subject, body=body),
            }
        )
    return payload


def build_html(rows: list[dict[str, Any]], profile: dict[str, Any]) -> str:
    listings = _serialize_listings(rows, profile)
    subject = html.escape((profile.get("email_subject") or "Room Rental Inquiry by Aug 18").strip())
    sample_body = html.escape(standard_apply_message(profile, "https://example.com/listing"))
    listings_json = json.dumps(listings, ensure_ascii=False)
    unapplied_count = sum(1 for item in listings if item["unapplied"])
    generated = html.escape(__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"))

    rows_html = []
    for index, item in enumerate(listings, 1):
        title = html.escape(item["title"][:90])
        price = item.get("price")
        price_label = html.escape(f"${price}/mo" if price else "N/A")
        hood = html.escape(item["neighborhood"])
        url = html.escape(item["url"])
        source = item.get("source") or "craigslist"
        badge = "📘" if source == "facebook" else ""
        status = "To apply" if item["unapplied"] else "Applied"
        status_class = "status-todo" if item["unapplied"] else "status-done"
        gmail_url = html.escape(item["gmailUrl"])
        listing_id = html.escape(item["id"])
        to_hint = ""
        if not item.get("to"):
            to_hint = '<p class="hint">Add Craigslist reply address in To after draft opens.</p>'

        rows_html.append(
            f"""
      <article class="listing" data-id="{listing_id}" data-unapplied="{str(item['unapplied']).lower()}">
        <div class="listing-main">
          <div class="listing-top">
            <span class="rank">{index}</span>
            <div>
              <h2>{title} {badge}</h2>
              <p class="meta">{price_label} · {hood}</p>
            </div>
            <span class="status {status_class}">{status}</span>
          </div>
          <div class="actions">
            <a class="button secondary" href="{url}" target="_blank" rel="noopener noreferrer">Open listing</a>
            <a class="button gmail-draft" href="{gmail_url}" target="_blank" rel="noopener noreferrer"
               data-listing-id="{listing_id}">Gmail draft</a>
          </div>
          {to_hint}
        </div>
      </article>"""
        )

    cards = "\n".join(rows_html) if rows_html else (
        '<p class="empty">No matches yet. Run <code>python run.py</code> locally first.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Room listings — apply</title>
  <style>
    :root {{
      --bg: #f5f5f7;
      --card: #fff;
      --text: #1d1d1f;
      --muted: #6e6e73;
      --blue: #0071e3;
      --green: #248a3d;
      --border: #d2d2d7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1.25rem 1rem 2.5rem;
      background: var(--bg);
      color: var(--text);
    }}
    header.page {{
      max-width: 760px;
      margin: 0 auto 1rem;
    }}
    h1 {{ margin: 0 0 0.25rem; font-size: 1.45rem; }}
    .sub {{ margin: 0; color: var(--muted); line-height: 1.45; }}
    .stats {{
      margin-top: 0.75rem;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    details.message {{
      max-width: 760px;
      margin: 0 auto 1rem;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 0.75rem 1rem;
    }}
    details.message summary {{
      cursor: pointer;
      font-weight: 600;
    }}
    details.message pre {{
      white-space: pre-wrap;
      font: inherit;
      line-height: 1.45;
      margin: 0.75rem 0 0;
      color: var(--muted);
    }}
    .listings {{
      max-width: 760px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}
    .listing {{
      background: var(--card);
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 1rem 1.1rem;
    }}
    .listing.applied-local {{
      opacity: 0.55;
    }}
    .listing-top {{
      display: flex;
      gap: 0.75rem;
      align-items: flex-start;
    }}
    .rank {{
      font-weight: 700;
      color: var(--muted);
      min-width: 1.5rem;
    }}
    .listing h2 {{
      margin: 0;
      font-size: 1.05rem;
      line-height: 1.3;
    }}
    .meta {{ margin: 0.2rem 0 0; color: var(--muted); font-size: 0.92rem; }}
    .status {{
      margin-left: auto;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: 999px;
      white-space: nowrap;
    }}
    .status-todo {{ background: #e8f2ff; color: var(--blue); }}
    .status-done {{ background: #eef7ee; color: var(--green); }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.85rem;
    }}
    .button {{
      display: inline-block;
      padding: 0.55rem 0.95rem;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.92rem;
      text-decoration: none;
      border: 0;
      cursor: pointer;
    }}
    .button {{
      background: var(--blue);
      color: #fff;
    }}
    .button.secondary {{
      background: #f0f0f2;
      color: var(--text);
    }}
    .hint {{
      margin: 0.55rem 0 0;
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .empty {{ color: var(--muted); }}
    code {{ font-size: 0.9em; }}
  </style>
</head>
<body>
  <header class="page">
    <h1>Room listings</h1>
    <p class="sub">Same inquiry for every listing. Tap <strong>Gmail draft</strong> → review in Gmail → send.</p>
    <p class="stats">{unapplied_count} to apply · {len(listings)} shown · updated {generated}</p>
  </header>

  <details class="message">
    <summary>Message template (subject: {subject})</summary>
    <pre>{sample_body}</pre>
  </details>

  <section class="listings">
{cards}
  </section>

  <script id="listings-data" type="application/json">{listings_json}</script>
  <script>
    const STORAGE_KEY = "appliedListingIds";

    function loadApplied() {{
      try {{
        return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
      }} catch (_) {{
        return new Set();
      }}
    }}

    function saveApplied(ids) {{
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
    }}

    function markApplied(id) {{
      const ids = loadApplied();
      ids.add(id);
      saveApplied(ids);
      const card = document.querySelector(`.listing[data-id="${{CSS.escape(id)}}"]`);
      if (!card) return;
      card.classList.add("applied-local");
      const status = card.querySelector(".status");
      if (status) {{
        status.textContent = "Draft opened";
        status.className = "status status-done";
      }}
    }}

    document.querySelectorAll(".gmail-draft").forEach((btn) => {{
      btn.addEventListener("click", () => {{
        const id = btn.getAttribute("data-listing-id");
        if (id) markApplied(id);
      }});
    }});

    loadApplied().forEach((id) => markApplied(id));
  </script>
</body>
</html>"""


def run(*, limit: int = DEFAULT_LIMIT) -> Path:
    init_db()
    profile = load_profile()
    rows = _listing_rows(limit)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_html(rows, profile), encoding="utf-8")
    return OUTPUT_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Cloudflare Pages listing list")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max listings")
    args = parser.parse_args(argv)
    try:
        path = run(limit=args.limit)
        rows = _listing_rows(args.limit)
        print(f"Wrote {len(rows)} listing(s) → {path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())