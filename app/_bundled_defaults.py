"""
Build-time bundled defaults.

This module is REWRITTEN by the build pipeline (build/build-deb.sh and
build/build-exe.bat) before PyInstaller picks it up, so .deb / .exe artifacts
ship with the right Supabase project, key, and (optionally) DB password
already filled in.

The dev-tree copy below stays empty so running from source does not pin
anyone to a specific cloud database — `app.config` will fall back to the
hardcoded Supabase URL/anon key default and finally to local SQLite.
"""

from __future__ import annotations

# Each key, when present, overrides the default in app/config.py.
# Recognised keys:
#   supabase_url        e.g. "https://abcdef.supabase.co"
#   supabase_anon_key   e.g. "sb_publishable_..."
#   supabase_db_password e.g. "the-database-password"
#   google_api_key      e.g. "AIzaSy..."
#   sender_name, sender_company, sender_website, sender_email
BUNDLED: dict = {}
