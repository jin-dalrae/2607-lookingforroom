#!/usr/bin/env python3
"""Generate listing-mails-communication.html — follow-up tracker for sent inquiries."""

from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from apply import load_profile
from channels import channel_icon, channel_label, normalize_channel
from db import (
    get_application_stats,
    get_channel_stats,
    get_communication_records,
    init_db,
)

OUTPUT_PATH = Path(__file__).parent / "listing-mails-communication.html"
FOLLOW_UP_AFTER_DAYS = 3

STATUS_LABELS = {
    "draft": ("Draft", "draft"),
    "sent": ("Sent — awaiting reply", "sent"),
    "replied": ("Landlord replied", "replied"),
    "toured": ("Toured", "toured"),
    "rejected": ("Rejected / gone", "rejected"),
    "accepted": ("Accepted", "accepted"),
}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_since(ts: str | None) -> int | None:
    dt = _parse_iso(ts)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return max(0, delta.days)


def _follow_up_text(profile: dict[str, Any], listing_url: str) -> str:
    template = (profile.get("follow_up_template") or "").strip()
    if not template:
        return (
            "Hi! Following up on my room inquiry — still interested. "
            "Is the room still available?\n\nThank you!"
        )
    blocks = template.split("\n\n")
    if listing_url and listing_url not in template:
        return f"{blocks[0]}\n\n{listing_url}\n\n" + "\n\n".join(blocks[1:])
    return template


def _gmail_search_url(subject: str) -> str:
    q = quote(f'subject:"{subject}"')
    return f"https://mail.google.com/mail/u/0/#search/{q}"


def _action_hint(row: dict[str, Any], days: int | None) -> str:
    status = row.get("status") or "draft"
    channel = normalize_channel(row.get("channel"), default="email")

    if status == "draft":
        if channel == "imessage":
            return "Send initial inquiry via iMessage (paste draft from /apply)"
        return "Send initial inquiry (Gmail Drafts or Craigslist reply)"

    if status == "replied":
        if channel == "imessage":
            return "Reply in Messages — schedule a viewing"
        return "Reply in Gmail — schedule a viewing"

    if status == "toured":
        return "Follow up on decision / lease terms"

    if status == "sent":
        via = "Messages" if channel == "imessage" else "email"
        if channel == "imessage":
            note = " (inbox scan won't see iMessage — mark /replied when they answer)"
        else:
            note = ""
        if days is not None and days >= FOLLOW_UP_AFTER_DAYS:
            return f"No reply in {days} days — follow up in {via}{note}"
        if days is not None:
            return f"Sent {days} day(s) ago via {via} — wait or gentle follow-up{note}"
        return f"Awaiting landlord reply via {via}{note}"
    return ""


def _row_fields(row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Normalize one communication record for table rendering."""
    title = (row.get("title") or "Untitled")[:80]
    price = row.get("price")
    hood = row.get("neighborhood") or "Unknown"
    url = row.get("url") or ""
    status = row.get("status") or "draft"
    label, css = STATUS_LABELS.get(status, (status, "other"))
    sent_at = row.get("sent_at") or ""
    sent_display = sent_at[:10] if sent_at else ""
    days = _days_since(sent_at or row.get("updated_at"))
    raw_channel = row.get("channel")
    channel_key = normalize_channel(raw_channel, default="email")
    reply_snip = row.get("last_reply_snippet")
    needs_follow = (
        status == "sent"
        and days is not None
        and days >= FOLLOW_UP_AFTER_DAYS
        and (not reply_snip or channel_key == "imessage")
    )
    return {
        "title": title,
        "price": price,
        "price_sort": int(price) if price is not None else 99999,
        "hood": hood,
        "url": url,
        "status": status,
        "status_label": label,
        "status_css": css,
        "sent_display": sent_display,
        "sent_sort": sent_display or "9999-99-99",
        "days": days if days is not None and status in ("sent", "replied") else "",
        "days_sort": days if days is not None and status in ("sent", "replied") else -1,
        "channel_key": channel_key,
        "channel_label": channel_label(raw_channel),
        "channel_icon": channel_icon(raw_channel),
        "source": row.get("source") or "craigslist",
        "action": _action_hint(row, days),
        "follow_up": _follow_up_text(profile, url),
        "reply_snip": str(reply_snip)[:200] if reply_snip else "",
        "notes": str(row.get("notes") or ""),
        "needs_follow": needs_follow,
        "gmail_link": _gmail_search_url(
            str(profile.get("email_subject") or "Room Rental Inquiry")
        ),
    }


def _table_row(fields: dict[str, Any], index: int) -> str:
    title = html.escape(fields["title"])
    hood = html.escape(fields["hood"])
    url = html.escape(fields["url"])
    status_label = html.escape(fields["status_label"])
    status_css = fields["status_css"]
    channel_label_text = html.escape(fields["channel_label"])
    channel_icon_char = fields["channel_icon"]
    action = html.escape(fields["action"])
    sent_display = html.escape(fields["sent_display"] or "—")
    days = fields["days"]
    days_display = html.escape(f"{days}d" if days != "" else "—")
    price = fields["price"]
    price_display = html.escape(f"${price}" if price else "—")
    follow_up = html.escape(fields["follow_up"])
    reply_snip = html.escape(fields["reply_snip"])
    notes = html.escape(fields["notes"])
    gmail_link = html.escape(fields["gmail_link"])
    channel_key = fields["channel_key"]
    needs_follow = fields["needs_follow"]
    row_class = "needs-follow" if needs_follow else ""

    reply_cell = ""
    if reply_snip and channel_key != "imessage":
        reply_cell = f'<div class="cell-sub">Gmail: {reply_snip}</div>'
    elif channel_key == "imessage" and fields["status"] == "sent":
        reply_cell = '<div class="cell-sub imessage-note">Use /replied when they answer</div>'
    if notes:
        reply_cell += f'<div class="cell-sub">Note: {notes}</div>'

    gmail_btn = ""
    if channel_key != "imessage":
        gmail_btn = (
            f'<a class="link-btn" href="{gmail_link}" target="_blank" '
            f'rel="noopener noreferrer">Gmail</a>'
        )

    detail_row = ""
    if fields["status"] in ("sent", "replied") or needs_follow:
        detail_row = f"""
        <tr class="detail-row" data-detail-for="{index}" hidden>
          <td colspan="10">
            <details class="follow-up" {'open' if needs_follow else ''}>
              <summary>Follow-up message</summary>
              <textarea rows="6" readonly>{follow_up}</textarea>
            </details>
          </td>
        </tr>
        """

    search_blob = html.escape(
        f"{fields['title']} {fields['hood']} {fields['channel_label']} "
        f"{fields['status_label']} {fields['action']}".lower()
    )

    return f"""
    <tr class="data-row {row_class}"
        data-index="{index}"
        data-search="{search_blob}"
        data-status="{html.escape(fields['status'])}"
        data-channel="{html.escape(channel_key)}"
        data-neighborhood="{html.escape(fields['hood'].lower())}"
        data-needs-follow="{'1' if needs_follow else '0'}"
        data-price="{fields['price_sort']}"
        data-days="{fields['days_sort']}"
        data-sent="{html.escape(fields['sent_sort'])}"
        data-title="{html.escape(fields['title'].lower())}">
      <td class="num">{index}</td>
      <td class="title-cell">
        <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
        {reply_cell}
      </td>
      <td class="num" data-col="price">{price_display}</td>
      <td>{hood}</td>
      <td><span class="badge badge-{status_css}">{status_label}</span></td>
      <td><span class="badge badge-channel">{channel_icon_char} {channel_label_text}</span></td>
      <td class="num" data-col="sent">{sent_display}</td>
      <td class="num" data-col="days">{days_display}</td>
      <td class="action-cell">{action}</td>
      <td class="links-cell">
        <a class="link-btn" href="{url}" target="_blank" rel="noopener noreferrer">Listing</a>
        {gmail_btn}
        <button type="button" class="link-btn toggle-detail" data-index="{index}">Follow-up</button>
      </td>
    </tr>
    {detail_row}
    """


def _channel_stats_line(channel_stats: dict[str, dict[str, int]]) -> str:
    parts: list[str] = []
    for ch, counts in sorted(channel_stats.items()):
        sent = counts.get("sent", 0)
        replied = counts.get("replied", 0)
        draft = counts.get("draft", 0)
        if sent or replied or draft:
            label = channel_label(ch)
            bits = []
            if draft:
                bits.append(f"{draft} draft")
            if sent:
                bits.append(f"{sent} sent")
            if replied:
                bits.append(f"{replied} replied")
            parts.append(f"{channel_icon(ch)} {label}: {', '.join(bits)}")
    return " · ".join(parts) if parts else ""


def build_html(
    rows: list[dict[str, Any]],
    profile: dict[str, Any],
    stats: dict[str, int],
    channel_stats: dict[str, dict[str, int]],
) -> str:
    table_rows = "\n".join(
        _table_row(_row_fields(row, profile), i)
        for i, row in enumerate(rows, 1)
    )
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    by_channel = _channel_stats_line(channel_stats)
    channel_row = (
        f'<p class="hint"><strong>By channel:</strong> {html.escape(by_channel)}</p>'
        if by_channel
        else ""
    )
    empty_state = (
        '<p class="hint">No active applications. Send inquiries first.</p>'
        if not rows
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Listing mail communication</title>
  <style>
    :root {{
      --bg: #f5f5f7;
      --card: #fff;
      --text: #1d1d1f;
      --muted: #6e6e73;
      --blue: #0071e3;
      --green: #248a3d;
      --orange: #bf4800;
      --purple: #8944ab;
      --border: #d2d2d7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1.25rem 1.5rem 2rem;
      background: var(--bg);
      color: var(--text);
    }}
    h1 {{ margin: 0 0 0.25rem; font-size: 1.5rem; }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
      margin: 0.75rem 0 1rem;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .stat strong {{ color: var(--text); }}
    .hint {{ color: var(--muted); font-size: 0.9rem; line-height: 1.45; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.65rem 1rem;
      align-items: center;
      background: var(--card);
      border-radius: 12px;
      padding: 0.85rem 1rem;
      margin: 1rem 0 0.75rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    }}
    .toolbar label {{
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .toolbar input[type="search"],
    .toolbar select {{
      font: inherit;
      padding: 0.45rem 0.6rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      min-width: 10rem;
    }}
    .toolbar input[type="search"] {{ min-width: 14rem; }}
    .toolbar .check-label {{
      flex-direction: row;
      align-items: center;
      text-transform: none;
      font-size: 0.88rem;
      color: var(--text);
      font-weight: 500;
      gap: 0.4rem;
      margin-top: 1rem;
    }}
    .row-count {{
      margin-left: auto;
      font-size: 0.88rem;
      color: var(--muted);
      align-self: flex-end;
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--card);
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: #f9f9fb;
      border-bottom: 2px solid var(--border);
      padding: 0.65rem 0.75rem;
      text-align: left;
      white-space: nowrap;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      cursor: pointer;
      user-select: none;
    }}
    thead th:hover {{ color: var(--text); }}
    thead th.sorted-asc::after {{ content: " ▲"; font-size: 0.65rem; }}
    thead th.sorted-desc::after {{ content: " ▼"; font-size: 0.65rem; }}
    thead th.no-sort {{ cursor: default; }}
    tbody tr.data-row {{ border-bottom: 1px solid #ececef; }}
    tbody tr.data-row:hover {{ background: #fafafa; }}
    tbody tr.needs-follow {{ background: #fff8f2; }}
    tbody tr.needs-follow:hover {{ background: #fff3ea; }}
    tbody td {{
      padding: 0.6rem 0.75rem;
      vertical-align: top;
      line-height: 1.4;
    }}
    tbody td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .title-cell a {{
      color: var(--text);
      font-weight: 600;
      text-decoration: none;
    }}
    .title-cell a:hover {{ color: var(--blue); text-decoration: underline; }}
    .cell-sub {{
      margin-top: 0.25rem;
      font-size: 0.8rem;
      color: var(--muted);
      max-width: 28rem;
    }}
    .action-cell {{ max-width: 16rem; font-size: 0.82rem; }}
    .links-cell {{ white-space: nowrap; }}
    .badge {{
      display: inline-block;
      font-size: 0.68rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      padding: 0.18rem 0.45rem;
      border-radius: 6px;
      white-space: nowrap;
    }}
    .badge-sent {{ background: #e8f0fe; color: var(--blue); }}
    .badge-replied {{ background: #e8f5e9; color: var(--green); }}
    .badge-draft {{ background: #f0f0f2; color: var(--muted); }}
    .badge-toured {{ background: #f3e8ff; color: var(--purple); }}
    .badge-channel {{ background: #f0f0f2; color: var(--text); }}
    .imessage-note {{ color: #5e5ce6; }}
    .link-btn {{
      display: inline-block;
      margin-right: 0.35rem;
      padding: 0.2rem 0.5rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #f5f5f7;
      color: var(--text);
      font-size: 0.78rem;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
    }}
    .link-btn:hover {{ background: #e8e8ed; }}
    tr.detail-row td {{
      background: #fafafa;
      padding: 0.5rem 0.75rem 0.85rem;
      border-bottom: 1px solid var(--border);
    }}
    details.follow-up summary {{
      cursor: pointer;
      font-weight: 600;
      font-size: 0.88rem;
      color: var(--blue);
    }}
    textarea {{
      width: 100%;
      margin-top: 0.5rem;
      font: inherit;
      line-height: 1.45;
      padding: 0.65rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      resize: vertical;
    }}
    code {{ background: #e8e8ed; padding: 0.1rem 0.35rem; border-radius: 4px; }}
    tr.hidden {{ display: none; }}
  </style>
</head>
<body>
  <h1>Listing mail communication</h1>
  <p class="hint">Sort by clicking column headers. Orange rows = no reply in {FOLLOW_UP_AFTER_DAYS}+ days.
    iMessage threads are tracked manually (not Gmail).</p>
  {channel_row}
  <div class="stats">
    <span class="stat">Draft <strong>{stats.get('draft', 0)}</strong></span>
    <span class="stat">Sent <strong>{stats.get('sent', 0)}</strong></span>
    <span class="stat">Replied <strong>{stats.get('replied', 0)}</strong></span>
    <span class="stat">Rejected <strong>{stats.get('rejected', 0)}</strong></span>
  </div>
  <p class="hint">Generated {generated}. Refresh: <code>python communication_page.py --open</code></p>

  <div class="toolbar">
    <label>Search
      <input type="search" id="filter-search" placeholder="Title, area, status…">
    </label>
    <label>Status
      <select id="filter-status">
        <option value="">All</option>
        <option value="draft">Draft</option>
        <option value="sent">Sent</option>
        <option value="replied">Replied</option>
        <option value="toured">Toured</option>
      </select>
    </label>
    <label>Channel
      <select id="filter-channel">
        <option value="">All</option>
        <option value="email">Gmail</option>
        <option value="imessage">iMessage</option>
        <option value="craigslist">Craigslist</option>
        <option value="facebook">Facebook</option>
        <option value="phone">Phone</option>
      </select>
    </label>
    <label class="check-label">
      <input type="checkbox" id="filter-follow"> Needs follow-up ({FOLLOW_UP_AFTER_DAYS}+ days)
    </label>
    <span class="row-count" id="row-count"></span>
  </div>

  {empty_state}
  <div class="table-wrap">
    <table id="comm-table">
      <thead>
        <tr>
          <th data-sort="index" class="sorted-asc">#</th>
          <th data-sort="title">Title</th>
          <th data-sort="price">$/mo</th>
          <th data-sort="neighborhood">Area</th>
          <th data-sort="status">Status</th>
          <th data-sort="channel">Channel</th>
          <th data-sort="sent">Sent</th>
          <th data-sort="days">Days</th>
          <th class="no-sort">Next step</th>
          <th class="no-sort">Links</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>

  <script>
  (function () {{
    const table = document.getElementById('comm-table');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const searchInput = document.getElementById('filter-search');
    const statusSelect = document.getElementById('filter-status');
    const channelSelect = document.getElementById('filter-channel');
    const followCheck = document.getElementById('filter-follow');
    const rowCount = document.getElementById('row-count');
    let sortKey = 'index';
    let sortDir = 1;

    function dataRows() {{
      return Array.from(tbody.querySelectorAll('tr:not(.detail-row)'));
    }}

    function detailFor(index) {{
      return tbody.querySelector('tr.detail-row[data-detail-for="' + index + '"]');
    }}

    function applyFilters() {{
      const q = (searchInput.value || '').trim().toLowerCase();
      const status = statusSelect.value;
      const channel = channelSelect.value;
      const needsFollow = followCheck.checked;
      let visible = 0;
      dataRows().forEach((row) => {{
        const matchSearch = !q || (row.dataset.search || '').includes(q);
        const matchStatus = !status || row.dataset.status === status;
        const matchChannel = !channel || row.dataset.channel === channel;
        const matchFollow = !needsFollow || row.dataset.needsFollow === '1';
        const show = matchSearch && matchStatus && matchChannel && matchFollow;
        row.classList.toggle('hidden', !show);
        const detail = detailFor(row.dataset.index);
        if (detail && detail.hidden) detail.classList.add('hidden');
        if (detail && !detail.hidden && !show) detail.classList.add('hidden');
        if (show) visible += 1;
      }});
      rowCount.textContent = visible + ' of ' + dataRows().length + ' shown';
    }}

    function sortValue(row, key) {{
      if (key === 'index') return parseInt(row.dataset.index, 10);
      if (key === 'price') return parseInt(row.dataset.price, 10);
      if (key === 'days') return parseInt(row.dataset.days, 10);
      if (key === 'sent') return row.dataset.sent || '';
      if (key === 'title') return row.dataset.title || '';
      if (key === 'neighborhood') return row.dataset.neighborhood || '';
      if (key === 'status') return row.dataset.status || '';
      if (key === 'channel') return row.dataset.channel || '';
      return row.dataset.index;
    }}

    function applySort() {{
      const rows = dataRows();
      rows.sort((a, b) => {{
        const av = sortValue(a, sortKey);
        const bv = sortValue(b, sortKey);
        if (av < bv) return -1 * sortDir;
        if (av > bv) return 1 * sortDir;
        return parseInt(a.dataset.index, 10) - parseInt(b.dataset.index, 10);
      }});
      rows.forEach((row) => {{
        tbody.appendChild(row);
        const detail = detailFor(row.dataset.index);
        if (detail) tbody.appendChild(detail);
      }});
      table.querySelectorAll('thead th[data-sort]').forEach((th) => {{
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (th.dataset.sort === sortKey) {{
          th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
        }}
      }});
    }}

    table.querySelectorAll('thead th[data-sort]').forEach((th) => {{
      th.addEventListener('click', () => {{
        const key = th.dataset.sort;
        if (sortKey === key) sortDir *= -1;
        else {{ sortKey = key; sortDir = 1; }}
        applySort();
      }});
    }});

    [searchInput, statusSelect, channelSelect, followCheck].forEach((el) => {{
      el.addEventListener('input', applyFilters);
      el.addEventListener('change', applyFilters);
    }});

    tbody.addEventListener('click', (e) => {{
      const btn = e.target.closest('.toggle-detail');
      if (!btn) return;
      const detail = detailFor(btn.dataset.index);
      if (detail) detail.hidden = !detail.hidden;
    }});

    applySort();
    applyFilters();
  }})();
  </script>
</body>
</html>
"""


def run(*, check_mail: bool = False, open_browser: bool = False) -> Path:
    init_db()
    if check_mail:
        try:
            import mail_monitor

            if mail_monitor.gmail_configured():
                mail_monitor.check_inbox()
            else:
                print("Gmail not configured — skipping inbox check.", file=sys.stderr)
        except Exception as exc:
            print(f"mail_monitor warning: {exc}", file=sys.stderr)

    profile = load_profile()
    rows = get_communication_records()
    stats = get_application_stats()
    channel_stats = get_channel_stats()
    OUTPUT_PATH.write_text(
        build_html(rows, profile, stats, channel_stats),
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} row(s) → {OUTPUT_PATH.resolve()}")

    if open_browser:
        import subprocess

        subprocess.run(["open", str(OUTPUT_PATH.resolve())], check=False)

    return OUTPUT_PATH.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build listing-mails-communication.html")
    parser.add_argument(
        "--check-mail",
        action="store_true",
        help="Run mail_monitor.py before generating the page",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the HTML page in the default browser",
    )
    args = parser.parse_args(argv)
    try:
        run(check_mail=args.check_mail, open_browser=args.open)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())