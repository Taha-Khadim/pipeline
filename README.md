# Lumora Code — Client Pipeline

A local-first **client hunting + sales pipeline** tool for freelancers and
agencies. Find small businesses, enrich their contact info (email, phone,
website, socials), score them with AI, and generate personalized cold
outreach — all from one app, on your own machine.

> Priority is given to **businesses without a website** — the highest-value
> prospects for any web-development pitch.

## Features

- **Discover leads** from Google Maps + Bing Local in parallel.
- **18 countries / 600+ cities** preloaded, with search-as-you-type.
- **70+ industries** preconfigured (dentists, salons, plumbers, lawyers, …).
- **Contact enrichment** — emails, phones, social links scraped from the
  business' website + extra search-engine fallbacks for sites that don't
  exist online.
- **AI lead research + scoring** (Google Gemini, free tier).
- **AI-generated outreach** — cold emails, call scripts, DMs, follow-ups.
- **Pipeline dashboard** with status funnel, charts, and KPIs.
- **Always Supabase Postgres** — every install reads from / writes to the
  same cloud database. No local SQLite, no per-machine drift.
- **Dark + light themes**.

## Install

### Ubuntu / Debian

```bash
sudo apt install ./lumora-pipeline_1.0.4_amd64.deb
```

Then launch from your app menu (**Lumora Code — Client Pipeline**) or run:

```bash
lumora-pipeline
```

### Windows

Double-click `lumora-pipeline-setup.exe` and follow the wizard.
A desktop shortcut is created automatically. Launch by double-clicking it.

> Both installers bundle Python and a headless Chromium — **no other
> software needs to be installed.**

## First-time setup

1. Launch the app — your default browser opens to the dashboard.
2. Go to **Settings** in the sidebar.
3. Paste your free Google Gemini key from
   <https://aistudio.google.com/app/apikey> and click **Test connection**.
4. (Optional) Fill in your name + company + website so generated emails
   are signed correctly.
5. Click **Discover** in the sidebar to start finding leads.

### Cloud database

The bundled `.deb` / `.exe` ship with a working Supabase Postgres
connection baked in (IPv4-friendly pooler URL). Open
**http://127.0.0.1:8765/settings** to confirm — the badge should read
**Supabase Postgres** and the **Test connection** button reports the
current row count.

To point Lumora at **your own** Supabase project instead:

1. Open <https://supabase.com/dashboard> → your project → **SQL Editor**
   → **New query** → paste the contents of
   `scripts/supabase_migration.sql` (or click *View migration SQL* on
   the Settings page) and run it. The script is idempotent.
2. In Supabase: **Settings → Database** → copy the **Connection pooling**
   URL (the IPv4-friendly one — works on every network, including
   IPv6-disabled ISPs).
3. In Lumora: **Settings → Supabase Database → Advanced: custom
   connection URL** → paste it → **Save & switch to Supabase**.
   The engine reloads on the spot — no restart needed.

You can also run the helper from a terminal:

```bash
python scripts/setup_supabase.py
```

## Build from source

You'll need Python 3.10+, `dpkg-deb` and `fakeroot` for the Linux build,
and Inno Setup for the Windows build.

```bash
git clone <repo>
cd pipeline
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# Build the Ubuntu .deb (output: build/dist/*.deb)
bash build/build-deb.sh

# Build the Windows installer (run inside a Windows venv)
build\build-exe.bat
```

Or just run from source for development:

```bash
python launcher.py
```

## Where is my data stored?

| OS      | Location                                                        |
|---------|-----------------------------------------------------------------|
| Linux   | `~/.local/share/lumora-pipeline/`                               |
| Windows | `%APPDATA%\LumoraPipeline\`                                     |
| macOS   | `~/Library/Application Support/LumoraPipeline/`                 |

This contains `settings.json` (your API keys + an optional override
Supabase URL) and `screenshots/`. **All** lead, outreach, and scrape
rows live in your Supabase Postgres project — there is no local
database file.

Set `LUMORA_DATA_DIR=/some/path` to override the location.

## Pre-baking Supabase credentials into a custom build

If you're building your own .deb / .exe and want it to point at a
*different* Supabase project (e.g. for distributing to a small team),
set these env vars before running the build script:

```bash
# Easiest: paste the full pooler URL and you're done.
export LUMORA_BUNDLED_DATABASE_URL='postgresql://postgres.PROJECT_REF:DB_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres'

# Optional extras:
export LUMORA_BUNDLED_SUPABASE_URL='https://PROJECT_REF.supabase.co'
export LUMORA_BUNDLED_SUPABASE_KEY='sb_publishable_xxx'
export LUMORA_BUNDLED_GOOGLE_API_KEY='AIzaSy...'

bash build/build-deb.sh        # or build\build-exe.bat on Windows
```

The values get written into `app/_bundled_defaults.py` for the duration
of the build and are restored back to empty afterwards, so nothing leaks
into the dev tree or git history.

## Tech stack

Python · FastAPI · SQLAlchemy (async) · Supabase Postgres (asyncpg) ·
Playwright · Jinja2 · Tailwind CSS · Alpine.js · Chart.js · Google Gemini
· PyInstaller.
