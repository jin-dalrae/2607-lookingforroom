# Looking for Room

**https://github.com/jin-dalrae/2607-lookingforroom**

Local room finder + browser apply queue (Craigslist / Facebook → filter → track outreach).

---

## For people

1. Open this link in a coding agent (Claude Code, Cursor, Codex, Grok, …):  
   **https://github.com/jin-dalrae/2607-lookingforroom**
2. Say only: **“Set me up for Looking for Room.”**
3. Answer the agent’s questions. It installs everything, starts the app, and opens the queue.

You do **not** need git, terminals, or a long prompt. The agent asks; you answer.

---

## For coding agents

You install, configure, run, and maintain the app. Never tell the user to `git clone` or write a criteria essay — **you interview them**.

### 1. First message from user ≈ “set me up”

Immediately ask **these questions** (one batch is fine). Do not invent answers.

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

Write answers into `profile.yaml` and `lfr/config.py` (`SEARCH_CRITERIA`, `LOCATION_ALLOWED` / `LOCATION_EXCLUDE`, scout URLs).

### 2. Bootstrap (you run this)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# playwright install chromium   # only if they want Facebook scout
# fill profile.yaml + lfr/config.py from the interview
python -c "from lfr.db import init_pipeline_tables; init_pipeline_tables()"
python run.py
DETAIL_BACKFILL_LIMIT=0 python listings_page.py
scripts/workers.sh start
# open http://127.0.0.1:8765/
```

| URL | Role |
|-----|------|
| http://127.0.0.1:8765/ | Apply queue |
| http://127.0.0.1:8787/ | API |

Workers: `scripts/workers.sh start|restart|status|stop` · logs `.run/logs/`

### 3. Gmail — ask later

When they need drafts or reply monitoring, ask for a Gmail **App Password** (not their normal password):

1. [2-Step Verification](https://myaccount.google.com/security)  
2. [App passwords](https://myaccount.google.com/apppasswords) → Mail  

```env
GMAIL_ADDRESS=…
GMAIL_PASSWORD=…   # 16-char app password
```

### 4. Scoring — use a subagent

`python filter.py` / `run.py` = local heuristics.  
For a shortlist: spawn a **subagent** to rank **to_apply** against their criteria; return fit / red flags. Don’t rewrite application history.

### 5. Day-to-day

| Task | Command |
|------|---------|
| Refresh | `python run.py` then `scripts/workers.sh restart` |
| Scout only | `python scout.py` |
| Export | `python listings_page.py` |
| Facebook | `python scout_facebook.py login` then `poll` |
| Replies | `python mail_monitor.py` |

### Do not

- Make the user write a long setup prompt or run git/shell  
- Wipe application history or bulk-mark neighborhoods Gone (use location filters)  
- Re-scrape listings already in the DB  
- Require cloud deploy or extra API keys  

Local only. User still sends messages; you find rooms and track status.
