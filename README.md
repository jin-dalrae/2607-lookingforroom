# Looking for Room

**https://github.com/jin-dalrae/2607-lookingforroom**

Local room finder + browser apply queue (Craigslist / Facebook → filter → track outreach).

![Apply queue UI — filter, memo, Apply / Sent / Skip](docs/queue-ui.png)

---

## For people

1. Open this link in a coding agent (Claude Code, Cursor, Codex, Grok, …):  
   **https://github.com/jin-dalrae/2607-lookingforroom**
2. Say only: **“Set me up for Looking for Room.”**
3. Answer the agent’s questions. It installs everything, starts the local server, and opens the queue.

You do **not** need git, terminals, or a long prompt. The agent asks; you answer.

### Day to day (you drive this)

1. Open your **coding agent** if the local server isn’t running yet — say *“start the Looking for Room server”*.
2. Open the queue: **http://127.0.0.1:8765/**
3. Click **Run Scrape** when you want **new listings** (screenshot above — blue button next to Map).
4. Work the table: memo, Apply, Sent, Skip, etc.

The agent does **not** auto-scrape or auto-mail every day. Only when you ask, or when you click **Run Scrape**.

### Your tool is the web queue

| In the UI | What it does |
|-----------|----------------|
| **Run Scrape** | Pull + score new listings (main way to refresh) |
| **Search / status / source / max $/mo** | Filter the table (e.g. To apply only) |
| **Liked only / Memo only** | Show starred or noted rows |
| **★** | Like / shortlist a listing |
| **MEMO** | Type a note or phone number — saved on that row |
| **Apply** | Starts outreach (see Craigslist / Facebook steps below) |
| **Sent** | Mark that you already contacted them |
| **Skip** | Not interested |
| **Delete / Scam** | Drop junk or flag scams |
| **Map** | Approximate pins by neighborhood |
| Stats | To apply / Applied / Replied / Visited / Skipped / Gone |

#### Apply — Craigslist

Craigslist hides the landlord address until you use **Reply** on their site.

1. Click **Apply** → opens the **listing** and a **Gmail draft** (subject + message filled; **To** usually empty).
2. On Craigslist: click **Reply** → copy the `…@…craigslist.org` email.
3. In Gmail: paste into **To** → Send.
4. Back in the queue: click **Sent**.

#### Apply — Facebook

1. Click **Apply** → message copied; listing opens.
2. Paste in Messenger / the thread → send.
3. Click **Sent** in the queue.

---

## For coding agents

You install, configure, and keep the **local server** available. You interview the user on first setup.  

**Do not** run ongoing scout / filter / mail jobs on a schedule unless the user **explicitly** asks. Day-to-day refresh is: user opens the queue → **Run Scrape**.

### 1. First message ≈ “set me up”

Ask these (one batch). Do not invent answers.

| # | Ask |
|---|-----|
| 1 | Full name? |
| 2 | Email? |
| 3 | Phone (for texts / WhatsApp)? |
| 4 | Move-in window (e.g. Aug 1–18, 2026)? |
| 5 | Max monthly budget ($)? |
| 6 | Preferred neighborhoods / areas? |
| 7 | Areas to exclude? |
| 8 | Anything else (room type, pets, lease length, …)? |
| 9 | Scout **Facebook Marketplace** too? (one-time browser login on their machine) |
| 10 | Set up **Gmail** for Craigslist drafts + reply detection? |

Write into `profile.yaml` + `lfr/config.py` (`SEARCH_CRITERIA`, `LOCATION_*`, scout URLs).

### 2. Bootstrap once

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# fill profile.yaml + lfr/config.py from the interview
python -c "from lfr.db import init_pipeline_tables; init_pipeline_tables()"
DETAIL_BACKFILL_LIMIT=0 python listings_page.py   # empty or existing queue JSON
scripts/workers.sh start
# open http://127.0.0.1:8765/
```

Then tell the user clearly:

> Servers are up. Open **http://127.0.0.1:8765/** and click **Run Scrape** whenever you want new listings. Work Apply / Sent / Skip / memos in that page. Come back to the agent only if something is broken or you want a change (criteria, Facebook login, Gmail, ranking help).

| URL | Role |
|-----|------|
| http://127.0.0.1:8765/ | Apply queue (user’s main screen) |
| http://127.0.0.1:8787/ | API — required for **Run Scrape**, drafts, status |

Workers: `scripts/workers.sh start|restart|status|stop` · logs `.run/logs/`

**Run Scrape** (UI → `POST /api/scrape`) runs the pipeline (`run.py` + export) in the background. Keep workers running so that button works.

Optional: one initial `python run.py` during setup if they want data before the first click — not required; prefer teaching **Run Scrape**.

### 3. Facebook setup (if they said yes)

1. `playwright install chromium`
2. `python scout_facebook.py login` — **never ask for FB password in chat**; they log in in the browser window, then press Enter.
3. Confirm: `python -c "from lfr.scout.session import session_configured; print(session_configured())"`
4. After that, **Run Scrape** / `run.py` can include Facebook when a session exists.

Re-login with `python scout_facebook.py login` only if polls fail.

### 4. Gmail + Craigslist (if they said yes, or when drafts/replies needed)

Ask later for a Gmail **App Password** (not their normal password):

1. [2-Step Verification](https://myaccount.google.com/security)  
2. [App passwords](https://myaccount.google.com/apppasswords) → Mail  

```env
GMAIL_ADDRESS=their@gmail.com
GMAIL_PASSWORD=xxxx xxxx xxxx xxxx
```

Verify: `python -c "from lfr.mail.gmail_creds import gmail_configured; print(gmail_configured())"`  
Restart workers so drafts work.

**User Apply path (explain once):** Apply → CL **Reply** → copy email → paste Gmail **To** → Send → **Sent** in queue.

**Reply detection:** only if asked — `python mail_monitor.py` or `--loop 300`. Do **not** start a mail loop unprompted.

### 5. Scoring / shortlist — only if asked

Default scores come from heuristics inside scrape/filter.  
If they want a judgment pass: spawn a **subagent** on **to_apply** vs their criteria. Don’t rewrite application history.

### 6. Commands (when the user asks — not automatic)

| User intent | What you run |
|-------------|----------------|
| Server / screen down | `scripts/workers.sh start` (or `restart`) + open http://127.0.0.1:8765/ |
| “Get new listings” via agent | Prefer: “Click **Run Scrape** in the queue.” Or, if they insist: `python run.py` + export / restart |
| Facebook re-login | `python scout_facebook.py login` |
| Check landlord replies | `python mail_monitor.py` |
| Change criteria | Edit config/profile, then they **Run Scrape** or you re-export |

### Do not

- Auto-run daily scout / mail / deploy without being asked  
- Make the user write a long setup prompt or run git/shell  
- Ask for Facebook or Gmail **login** passwords (App Password + browser login only)  
- Wipe application history or bulk-mark neighborhoods Gone  
- Re-scrape known listings unnecessarily  
- Require cloud deploy or extra API keys  

Local only. User owns the queue and **Run Scrape**; you set up and help on request.
