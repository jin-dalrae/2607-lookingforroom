# SF Room Finder

Automated pipeline to scout Craigslist for rooms in San Francisco and Oakland, filter by your criteria, rank matches, and draft outreach messages.

## Search criteria

| Setting | Value |
|---------|-------|
| Max rent | $1,300/mo |
| Room type | Private bedroom or small shared house (~3 people, ~2 roommates) |
| Reject | Shared bedroom, SRO/hostel, curtain/partition rooms, scams |
| Location | SF + Oakland |
| Transit | **Muni Metro/tram** (N-Judah, J-Church, etc.) preferred, then **Caltrain**, then BART; generic Muni bus is weaker |
| Move-in window | Aug 16–18, 2026 (±2 weeks flexible) |

Configured in `config.py` → `SEARCH_CRITERIA`.

## Setup

```bash
cd 2607-lookingforroom
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add API keys as needed:

```bash
cp .env.example .env
```

## Alerts

Get notified when new high-score listings appear (score ≥ 80). Duplicate alerts for the same listing are suppressed via `last_alerted_ids.json`.

### Interactive Telegram bot (recommended)

Start the bot, then open [@Rae_house_bot](https://t.me/Rae_house_bot) and tap **Start** once (saves your `chat_id` to `telegram_chat.json` for alerts):

```bash
python bot.py
```

Commands: `/top` `/apply` `/send` `/apps` `/mail` `/gmail` `/tram` `/caltrain` `/run` `/status` `/help`

- `/start` — register chat + show top 3 listings
- `/run` — full scout → filter → rank refresh (~3 min)
- `/apply` — copy-paste Craigslist draft for next listing to apply to
- `/send` — Gmail SMTP send **only if** listing text has a direct email (rare)
- `/sentall` — mark all drafts as sent after batch apply
- `/sent 3` or `/sent <url>` — mark one listing as sent
- `/applied` — mark last draft as sent (alias)
- `/replied` — mark last sent as replied when landlord responds
- `/mail` — scan Gmail inbox for landlord replies (auto-matches to sent applications)
- `/mail loop` — instructions for background polling every 5 minutes
- `/gmail status` — OAuth vs App Password vs not configured
- `/gmail auth` — one-time OAuth setup instructions
- `/apps` — pipeline dashboard + recent statuses
- `/prep` — five tour questions before a viewing
- `/tram` / `/caltrain` — transit-filtered top 5

Set `TELEGRAM_BOT_TOKEN` in `.env`. `TELEGRAM_CHAT_ID` is optional if you use `/start` on the bot (otherwise set it manually — see `notify.py`).

### One-shot pipeline alerts

```bash
# Telegram (default) — without tokens, prints a dry-run preview (IDs not marked)
python run.py --alert

# Slack instead
python run.py --alert --alert-channel slack

# Rank + alert only
python run.py --rank-only --alert
```

**Slack:** create an [Incoming Webhook](https://api.slack.com/messaging/webhooks) for your channel and set `SLACK_WEBHOOK_URL` in `.env`.

## Usage

**Full pipeline** (scout → score → rank → outreach):

```bash
python run.py
```

**Individual stages:**

```bash
python run.py --scout-only
python run.py --filter-only   # scores listings (Gemini + heuristic fallback)
python run.py --rank-only
python run.py --outreach-only
```

Show more/fewer top listings:

```bash
python run.py --top 10
```

## How to apply

Honest workflow — the bot finds and scores listings, but **most Craigslist replies still need you in a browser**.

1. **Bot finds + scores listings** — `python run.py` or `/run` in Telegram refreshes the pipeline.
2. **`/apply` gives a copy-paste message** — personalized from `profile.yaml` + listing flags (move-in hold ask, room size, utilities).
3. **You open the URL, use Craigslist email relay, paste the message** — Craigslist hides landlord emails; the Reply form needs a browser + `SERVICE_ID` token.
4. **`/sent` or `/applied` tracks it** — marks drafts as `sent` in the `applications` table.
5. **`/prep` before a tour** — five questions (utilities, house rules, move-in hold, room size, roommates).
6. **Follow-ups** — `mail_monitor` can detect landlord replies in Gmail; you still reply in the email thread yourself.

### Craigslist reality (read this)

| Expectation | Reality |
|-------------|---------|
| GCP / Gemini API key sends Gmail | **No** — API keys score listings only; they cannot send mail |
| Craigslist exposes landlord email | **No** — contact is via relay; listing HTML rarely has a direct `to` address |
| Gmail OAuth2 | **Yes** (recommended) — `python oauth_setup.py` once; `mail_monitor` + `send_mail` use Gmail API |
| App Password + SMTP/IMAP | **Yes** (fallback) — same `GMAIL_*` creds: (1) read inbox, (2) **send** when you know the recipient |
| `/send` on a Craigslist URL | Works **only** if description contains an extractable email (uncommon); otherwise use `/apply` + manual Reply |
| Auto-submit Craigslist Reply | **Not built** — would need Playwright/browser automation (TODO) |

When `/send` or `send_mail.py --listing-url` finds no email, open the listing link and paste your `/apply` draft into Craigslist Reply.

## Gmail OAuth2 setup (recommended)

OAuth avoids App Passwords and uses the Gmail API for inbox monitoring and sending.

### GCP setup (project `267981036962`)

1. **Enable Gmail API** — [Google Cloud Console](https://console.cloud.google.com/apis/library/gmail.googleapis.com?project=267981036962) → Enable.
2. **OAuth consent screen** — configure app name, support email, scopes (`gmail.readonly`, `gmail.send`). If External/testing, add your Gmail as a test user.
3. **Credentials** — APIs & Services → Credentials → **Create credentials** → OAuth 2.0 Client ID → **Desktop app**.
4. Copy **Client ID** and **Client secret** from the credentials page.

### Local setup

Add to `.env` (Client ID is already in `.env.example`; you must paste the **Client secret** yourself):

```
GMAIL_OAUTH_CLIENT_ID=267981036962-gj06904enh79gdv4mj3fbvi8gitkis35.apps.googleusercontent.com
GMAIL_OAUTH_CLIENT_SECRET=...   # from GCP Console → Credentials
GMAIL_ADDRESS=dalrae.jin.work@gmail.com
```

Run the one-time consent flow (opens browser):

```bash
python oauth_setup.py
# headless / SSH: python oauth_setup.py --headless
```

This saves `gmail_token.json` (gitignored). Verify:

```bash
python -c "import gmail_auth; print(gmail_auth.auth_status())"
```

**Telegram:** `/gmail status` · `/gmail auth`

**Fallback:** If OAuth is not set up, App Password (`GMAIL_APP_PASSWORD`) still works for IMAP + SMTP.

## Outbound email (Gmail API or SMTP)

Send inquiries when you have a **known recipient address** (landlord posted email in listing, Facebook lead, etc.).

**Setup:** OAuth (above) or App Password — see [Mailbox monitoring](#mailbox-monitoring).

**Subject / body** come from `profile.yaml`:
- `email_subject` (default: `"Room Rental Inquiry by Aug 18"`)
- `message_template` (+ listing-specific paragraphs via `apply.build_draft`)

```bash
# Preview without password or SMTP
python send_mail.py --dry-run --to landlord@example.com

# Direct send (no listing tracking)
python send_mail.py --to landlord@example.com

# Craigslist listing — sends only if description has a direct email
python send_mail.py --listing-url https://sfbay.craigslist.org/...
python send_mail.py --top 3          # 3rd ranked listing
python send_mail.py --dry-run --top 3
```

After a successful send tied to a listing, the app is marked `sent` with `channel='email'`.

**Telegram:** `/send` (next unapplied) or `/send 3` (ranked #3).

## Mailbox monitoring

Automatically detect landlord replies in Gmail, match them to sent Craigslist applications, update status to `replied`, and alert via Telegram.

### Setup (you must provide credentials)

**Option A — OAuth2 (recommended):** see [Gmail OAuth2 setup](#gmail-oauth2-setup-recommended) above.

**Option B — App Password (fallback):** Gmail IMAP requires a **Google App Password** — your regular Gmail password will not work.

1. **Enable 2-Step Verification** on your Google account:  
   https://myaccount.google.com/security

2. **Create an App Password** (choose Mail → Other device name):  
   https://myaccount.google.com/apppasswords  
   Google shows a 16-character password (e.g. `abcd efgh ijkl mnop`).

3. **Add to `.env`** (copy from `.env.example`):
   ```
   GMAIL_ADDRESS=dalrae.jin.work@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```
   Use the address you use for Craigslist email relay replies.

4. **Test** (dry-run if credentials missing):
   ```bash
   python mail_monitor.py --dry-run
   python mail_monitor.py              # one inbox check
   ```

### How it works

- **OAuth:** Gmail API `users.messages.list` + `get` on INBOX (last **14 days**).
- **Fallback:** `imap.gmail.com:993` (SSL) and scans INBOX emails from the **last 14 days**.
- Filters for likely landlord replies:
  - **From** contains `craigslist.org`, `reply.craigslist`, or `hous.craigslist`
  - **Or** subject/body mentions room, rental, listing, apartment, available, viewing
- **Matches** to your `sent` applications by:
  1. Craigslist post ID in email URLs/body (best)
  2. Fuzzy match of email subject to listing title
- **On match:** `sent` → `replied` in DB, Telegram alert with subject + snippet + listing link
- **Dedup:** processed `Message-ID`s stored in SQLite `mail_messages` table (no double-alerts)

### Ongoing monitoring

| Action | CLI | Telegram |
|--------|-----|----------|
| One inbox check | `python mail_monitor.py` | `/mail` |
| Poll every 5 min | `python mail_monitor.py --loop 300` | `/mail loop` (shows command) |
| Preview without updates | `python mail_monitor.py --dry-run` | — |

**Suggested cron** (every 5 minutes):

```cron
*/5 * * * * cd /path/to/2607-lookingforroom && .venv/bin/python mail_monitor.py >> logs/mail.log 2>&1
```

Keep marking applications `/sent` after you contact landlords — the monitor only matches against `sent` rows.

## Tracking applications

After you send Craigslist messages, sync the database so rankings and `/apply` skip listings you've already contacted.

**One-time catch-up** (e.g. after `batch_apply.html`):

```bash
python sync.py --catch-up    # mark all drafts as sent
python sync.py --status      # pipeline dashboard
```

**Ongoing tracking:**

| Action | CLI | Telegram |
|--------|-----|----------|
| Sent one listing | `python sync.py --url <url>` | `/sent <url>` or `/sent 3` (rank) |
| Sent batch of top N | `python sync.py --top 19` | `/sentall` (all drafts) |
| Landlord replied | `python mail_monitor.py` (auto) | `/mail` or `/replied` (manual) |
| View pipeline | `python sync.py --status` | `/apps` |

`/apps` shows: **sent · replied · toured · rejected · awaiting fresh** (unapplied ranked listings).

Statuses: `draft` → `sent` → `replied` → `toured` → `accepted` / `rejected`. Each sent row stores `channel` (default `craigslist`) and `sent_at`.

CLI equivalent:

```bash
python apply.py              # draft for next unapplied top listing
python apply.py --top 3      # draft for 3rd ranked listing
python apply.py <url_or_id>  # draft for a specific listing
```

Edit `profile.yaml` once with your name, move-in window, budget, and about-you bullets.

## Daily workflow

1. **Morning & evening** — run `python run.py` (or set a cron job every 6 hours; see `POLL_INTERVAL_HOURS` in `config.py`).
2. **Review top 5** — printed at the end of each run; use `/apply` or `python apply.py` for drafts.
3. **Send manually on Craigslist** — copy draft, paste into email relay, then `/applied`.
4. **Facebook groups** — this tool covers Craigslist only. Check these manually (see below).

### Suggested cron (every 6 hours)

```cron
0 */6 * * * cd /path/to/2607-lookingforroom && .venv/bin/python run.py >> logs/run.log 2>&1
```

## Manual Facebook group tips

Craigslist is automated; Facebook is still manual but often has better leads.

**Groups to join (search FB for exact names):**

- *San Francisco Housing, Rooms, Apartments, Sublets*
- *SF Bay Area Rooms and Apartments*
- *San Francisco Roommates*
- *Queer Housing SF* (if relevant)
- Neighborhood-specific: *Mission District Housing*, *Castro SF Housing*

**Daily FB routine (~15 min):**

1. Sort each group feed by **Recent posts**.
2. Filter mentally: own bedroom or small shared house, ≤$1,300, SF/Oakland, Aug move-in.
3. Save promising posts to a spreadsheet or Notes with link + contact.
4. Message within **2 hours** of posting — good rooms go fast.
5. Use the outreach template from `outreach.py`; mention your move-in dates upfront.

**Red flags:** wire transfers before viewing, no photos, price too good to be true, "room for couple" when you need solo.

## Project layout

```
profile.yaml   # Your applicant profile (name, move-in, budget)
config.py      # Search criteria, URLs, env
run.py         # CLI orchestrator
scout.py       # Craigslist fetcher
filter.py      # Gemini/heuristic scoring
rank.py        # Top-15 digest output
apply.py       # Application drafts + tour prep
outreach.py    # Batch drafts for top 3 (uses apply.py)
db.py          # SQLite storage (listings, scores, applications)
sync.py        # CLI catch-up for sent/replied tracking
notify.py      # Telegram / Slack alerts
bot.py         # Interactive Telegram bot (long polling)
gmail_auth.py    # Shared Gmail OAuth2 helpers
oauth_setup.py   # One-time OAuth consent CLI
mail_monitor.py  # Gmail API / IMAP monitor for landlord replies
send_mail.py     # Gmail API / SMTP outbound (when direct TO address known)
gmail_token.json # OAuth token (generated; gitignored)
listings.db    # Generated at runtime
telegram_chat.json  # Saved on /start (chat_id for alerts)
last_alerted_ids.json  # Tracks alerted listing IDs
```

## Search strategy

1. **Cast a wide net** — Craigslist `private_room=1` + max price in URL.
2. **Filter hard** — exclude shared-bedroom/SRO/couple listings in `filter.py`; shared kitchen/bath in a small house is OK.
3. **Rank by value** — lower rent + preferred neighborhoods (Mission, Castro, Noe, Bernal, etc.) score higher. Transit tiers in `config.py` → `TRANSIT_PREFERENCES`: Muni Metro/tram (+25), Caltrain (+22), BART (+15), Muni bus only (+5).
4. **Act fast** — run twice daily; reply same day with a short, friendly note and specific move-in dates.
5. **Supplement with FB** — many landlords post only on Facebook.
6. **View in person** — never send deposit without seeing the room and meeting roommates.