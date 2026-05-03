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
- **No data leaves your machine** — everything stored in a local SQLite DB.
- **Dark + light themes**.

## Install

### Ubuntu / Debian

```bash
sudo apt install ./lumora-pipeline_1.0.0_amd64.deb
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

This contains `pipeline.db` (SQLite), `settings.json`, and `screenshots/`.

Set `LUMORA_DATA_DIR=/some/path` to override.

## Tech stack

Python · FastAPI · SQLAlchemy (async) · SQLite · Playwright ·
Jinja2 · Tailwind CSS · Alpine.js · Chart.js · Google Gemini · PyInstaller.
