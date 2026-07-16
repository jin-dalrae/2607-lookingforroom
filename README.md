# Looking for Room — coding agent guide

**Repo:** https://github.com/jin-dalrae/2607-lookingforroom

This README is for **coding agents** (Claude Code, Cursor, Codex, Grok, Copilot, etc.).  
End users should clone this repo, open it in an agent, and describe their housing search in plain language. **You** (the agent) install, configure, run, and maintain the app.

---

## What this app is

Local room-hunting pipeline + browser **apply queue**:

1. **Scout** Craigslist (and optionally Facebook Marketplace)
2. **Filter / score** against move-in, budget, neighborhoods, room type
3. **Export** to `site/data.json` and serve a queue UI
4. **Track** outreach status in SQLite (`listings.db` + `applications`)

The **human** still sends messages (Craigslist Reply / Messenger / Gmail). The app finds listings, drafts copy, and remembers history.

Everything runs **locally**. There is no required cloud host, Pages deploy, or tunnel.

| Local URL | Role |
|-----------|------|
| http://127.0.0.1:8765/ | Apply queue UI |
| http://127.0.0.1:8765/map.html | Map pins |
| http://127.0.0.1:8787/ | Apply API (status, drafts, scrape trigger) |

---

## Agent bootstrap (do this in order)

### 0. Clone / open

```bash
git clone https://github.com/jin-dalrae/2607-lookingforroom.git
cd 2607-lookingforroom
```

### 1. Python env

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium        # only if user wants Facebook scout
```

### 2. Profile (`profile.yaml`)

Copy and fill from the user’s answers (or run `python setup.py` for interactive prompts):

```bash
cp profile.example.yaml profile.yaml
```

Required fields: `name`, `email`, `phone`, `move_in`, `budget`, `message_template`, `email_subject`.

Also map their search into **`lfr/config.py`**:

| Config | Purpose |
|--------|---------|
| `SEARCH_CRITERIA` | budget, move-in window, preferred / penalize neighborhoods |
| `LOCATION_ALLOWED` | SF whitelist terms |
| `LOCATION_EXCLUDE` | hard rejects (outer SF, Oakland, Emeryville, South SF, etc.) |
| `LOCATION_PREFERENCES` | score boosts for focus areas |
| `FACEBOOK_MARKETPLACE_SEARCHES` | FB query list |
| `lfr/scout/craigslist.py` → `SEARCH_URLS` | Craigslist area queries |

**Do not** leave South San Francisco / Oakland / Emeryville / Richmond / Sunset / Ingleside / Excelsior allowed if the user excluded them.

### 3. Gmail App Password (**required**)

Gmail is **not optional** for a complete setup. The apply API uses it for drafts; `mail_monitor.py` uses it for landlord replies.

Use a Google **App Password** (16 characters). **Never** put the user’s normal Gmail password in `.env`.

1. User enables [2-Step Verification](https://myaccount.google.com/security)
2. User creates an app password: [App passwords](https://myaccount.google.com/apppasswords) → Mail → “Looking for Room”
3. Write `.env` (start from `.env.example`):

```env
GMAIL_ADDRESS=user@gmail.com
GMAIL_PASSWORD=xxxx xxxx xxxx xxxx
```

Spaces in the app password are fine (stripped at runtime).  
Legacy alias: `GMAIL_APP_PASSWORD` also works.

Verify:

```bash
python -c "from lfr.mail.gmail_creds import gmail_configured, gmail_address; print(gmail_address(), gmail_configured())"
```

Expect `True`. If `False`, stop and fix Gmail before calling setup complete.

`python setup.py` also prompts for the app password and writes these keys.

**Only required secret:** `GMAIL_ADDRESS` + `GMAIL_PASSWORD`. Do not invent Gemini, Telegram, OAuth client, or deploy tokens.

### 4. Database + first export + servers

```bash
python -c "from lfr.db import init_pipeline_tables; init_pipeline_tables()"
DETAIL_BACKFILL_LIMIT=0 FB_TITLE_BACKFILL_LIMIT=0 POSTED_BACKFILL_LIMIT=0 python listings_page.py
scripts/workers.sh start
```

Open http://127.0.0.1:8765/ for the user.

| Command | Meaning |
|---------|---------|
| `scripts/workers.sh start` | Detached UI `:8765` + API `:8787` |
| `scripts/workers.sh restart` | Re-export queue + restart |
| `scripts/workers.sh status` | Health |
| `scripts/workers.sh stop` | Stop |

Logs: `.run/logs/`. PIDs: `.run/pids/`.

---

## Day-to-day agent operations

### Refresh listings

```bash
source .venv/bin/activate
python run.py                    # scout + local heuristic score + rank
# or focused:
python scout.py                  # Craigslist only
python filter.py                 # rescore with local heuristics
python listings_page.py          # export site/data.json
scripts/workers.sh restart       # export + bounce workers
```

Facebook (optional, needs prior login):

```bash
python scout_facebook.py login   # one-time headed browser
python scout_facebook.py poll
```

### Scoring — use a **subagent** (preferred)

Default pipeline scoring is **local heuristics only** (`python filter.py` / `run.py`). No cloud scoring product is required.

When the user wants a real judgment pass (or after a big scout), **spawn a subagent** instead of hand-waving scores:

1. Ensure heuristics have run: `python filter.py`
2. Export or read queue data (`site/data.json` or SQLite `listings` + `scores` + `applications`)
3. Spawn a **general-purpose or explore subagent** with a tight brief, e.g.:

   > Score and rank the current **to_apply** listings for this user.  
   > Criteria from `profile.yaml` + `lfr/config.py` (budget, move-in, preferred/excluded neighborhoods).  
   > Return a short ranked list (id, title, price, neighborhood, move-in fit, why fit / why not).  
   > Flag scams, shared bedrooms, wrong city, and stale posts.  
   > Do not mark applications Gone or rewrite history.

4. Present the subagent’s shortlist to the user in chat (and optionally note top picks).  
5. Re-export if the subagent or you changed config: `python listings_page.py` or `scripts/workers.sh restart`.

**Do not** require Gemini / GCP keys for scoring. If code still mentions `USE_GEMINI`, leave it off unless the user explicitly asks for that optional path.

### Mail / replies

```bash
python mail_monitor.py           # one-shot inbox match → mark replied
python mail_monitor.py --loop 300
```

---

## Rules — do not break user trust

1. **Never wipe outreach history**  
   Rows with `applications` status (`sent`, `replied`, `skipped`, `toured`, `draft`, `rejected`) are user history. Do not delete them to “clean” the queue.

2. **Out-of-area = filter, not bulk Gone**  
   Hard excludes go in `LOCATION_EXCLUDE` / allowed-zone logic. **Do not** mass-`UPDATE applications SET status='rejected'` for whole neighborhoods. Filtered listings simply leave **To apply**.

3. **No artificial listing cap**  
   Export is uncapped by default. Do not reintroduce a hard cap unless the user asks.

4. **Do not re-scrape known listings**  
   Detail HTTP is skipped when a listing already has description or an application row. Don’t force full re-fetches of the whole DB.

5. **No junk auto-memos**  
   Do not write notes like “Out of search area (…)”. Preserve user notes only.

6. **Secrets**  
   `.env`, `profile.yaml`, `listings.db`, `facebook_state.json` — never commit. Only `GMAIL_PASSWORD` app password for mail.

7. **Local only**  
   Do not push users into Cloudflare Pages, D1, tunnels, or other hosting unless they explicitly ask for a custom deploy. Default is local UI + API.

---

## How the pipeline fits together

```text
Craigslist / Facebook scouts
        ↓
  listings.db  (upsert by URL / listing id)
        ↓
  filter / score  (local heuristics)
        ↓
  optional: subagent rank/review of to_apply
        ↓
  listings_page.py → site/data.json
        ↓
  UI :8765  ←→  API :8787  (status, Gmail draft, scrape)
```

**Application statuses:** `draft` (to apply) → `sent` → `replied` → `toured` → `accepted` / `rejected` (gone), plus `skipped`.

**UI actions:** Apply (compose/copy) is client-side; **Mark sent / Skip / Gone / Like** hit the API and SQLite.

---

## Layout (where to edit)

```
setup.py                 Interactive profile + Gmail + start workers
run.py                   Pipeline orchestrator
api.py / listings_page.py / scout.py / filter.py / rank.py / …
profile.yaml             User identity + message templates
.env                     GMAIL_ADDRESS + GMAIL_PASSWORD only (required)

lfr/
  config.py              Search criteria, zones, exclude, FB searches
  scout/craigslist.py    SEARCH_URLS
  scout/facebook.py      Marketplace poll
  mail/                  App-password IMAP/SMTP
  web/api.py             Apply API
  db/                    SQLite access
  pipeline/export.py     site/data.json
  score/                 Local heuristic scoring

site/                    Static apply queue
scripts/workers.sh       UI + API lifecycle
```

Root `*.py` files are thin CLI entrypoints into `lfr/`.

---

## User-facing prompt (give them this)

> Open https://github.com/jin-dalrae/2607-lookingforroom in your coding agent and say:  
> “Read the README and set me up. Private room in SF, budget $____, move-in ______. Prefer ______. Exclude ______. Configure Gmail with my app password, start the servers, open the queue, scout listings, and use a subagent to rank the best to-apply rooms.”

---

## Quick checklist before you tell the user “ready”

- [ ] `.venv` + `pip install -r requirements.txt`
- [ ] `profile.yaml` filled from their criteria
- [ ] `lfr/config.py` neighborhoods match what they asked
- [ ] `.env` has `GMAIL_ADDRESS` + `GMAIL_PASSWORD` and `gmail_configured()` is `True`
- [ ] `scripts/workers.sh status` shows UI + API healthy
- [ ] Browser open on http://127.0.0.1:8765/
- [ ] Scout + heuristic filter run; optional **subagent** shortlist offered for top fits
