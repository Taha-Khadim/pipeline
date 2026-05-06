#!/usr/bin/env python3
"""
Interactive helper to wire Lumora up to a Supabase Postgres database.

What it does
------------
1. Asks for SUPABASE_URL, the anon/publishable key, and the DB password.
2. Tries to open a Postgres connection using those credentials.
3. Optionally runs scripts/supabase_migration.sql (or just prints the SQL
   so you can paste it into the Supabase SQL editor yourself).
4. Saves the values into the user-data settings.json so the running app
   immediately starts using Supabase on next request.

Usage
-----
    # from the project root, with the venv active:
    python scripts/setup_supabase.py

    # or non-interactive (CI / scripted install):
    SUPABASE_URL=https://abc.supabase.co \
    SUPABASE_KEY=sb_publishable_xxx \
    SUPABASE_DB_PASSWORD=your-db-password \
    python scripts/setup_supabase.py --yes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import (  # noqa: E402  (import after sys.path tweak)
    SETTINGS_FILE,
    save_settings_json,
    supabase_postgres_url,
)

MIGRATION_FILE = ROOT / "scripts" / "supabase_migration.sql"


def _prompt(label: str, default: str = "", secret: bool = False) -> str:
    suffix = f" [{default}]" if default and not secret else ""
    print(f"{label}{suffix}: ", end="", flush=True)
    if secret:
        try:
            import getpass

            value = getpass.getpass("")
        except Exception:
            value = sys.stdin.readline().strip()
    else:
        value = sys.stdin.readline().strip()
    return value or default


async def _try_connection(pg_url: str) -> tuple[bool, str]:
    try:
        import asyncpg  # type: ignore
    except ImportError:
        return False, (
            "asyncpg is not installed. Run `pip install asyncpg` (or "
            "`pip install -r requirements.txt`) first."
        )

    plain_url = pg_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        conn = await asyncpg.connect(plain_url, ssl=True, timeout=15)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()
    return True, "Connection OK"


async def _run_migration(pg_url: str) -> tuple[bool, str]:
    try:
        import asyncpg  # type: ignore
    except ImportError:
        return False, "asyncpg is not installed."

    sql = MIGRATION_FILE.read_text()
    plain_url = pg_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        conn = await asyncpg.connect(plain_url, ssl=True, timeout=30)
    except Exception as exc:
        return False, f"connect failed: {type(exc).__name__}: {exc}"
    try:
        await conn.execute(sql)
    except Exception as exc:
        await conn.close()
        return False, f"migration failed: {type(exc).__name__}: {exc}"
    finally:
        try:
            await conn.close()
        except Exception:
            pass
    return True, "Schema created / updated."


def main() -> int:
    parser = argparse.ArgumentParser(description="Wire Lumora to Supabase.")
    parser.add_argument(
        "--yes", action="store_true", help="Non-interactive — read values from env."
    )
    parser.add_argument(
        "--no-migrate",
        action="store_true",
        help="Skip running the migration SQL automatically.",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print the migration SQL to stdout and exit.",
    )
    args = parser.parse_args()

    if args.print_sql:
        print(MIGRATION_FILE.read_text())
        return 0

    print("\nLumora Code — Supabase setup")
    print("============================\n")
    print("Where to find these values: https://supabase.com/dashboard")
    print("  · Project URL          — Settings → Data API")
    print("  · Anon / publishable   — Settings → API Keys")
    print("  · Database password    — Settings → Database\n")

    if args.yes:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", os.environ.get("SUPABASE_ANON_KEY", "")).strip()
        password = os.environ.get(
            "SUPABASE_DB_PASSWORD", os.environ.get("SUPABASE_PASSWORD", "")
        ).strip()
        if not (url and password):
            print(
                "ERROR: --yes requires SUPABASE_URL and SUPABASE_DB_PASSWORD env vars.",
                file=sys.stderr,
            )
            return 2
    else:
        url = _prompt(
            "SUPABASE_URL", os.environ.get("SUPABASE_URL", "https://ailespxrkdfvureeleox.supabase.co")
        )
        key = _prompt(
            "Anon / publishable key",
            os.environ.get("SUPABASE_KEY", "sb_publishable_n5-DKZgPSLAoDN53NsdFdw_GLPLbhMF"),
        )
        password = _prompt("Database password (hidden)", secret=True)

    if not re.match(r"https?://[a-z0-9]+\.supabase\.co/?$", url, re.IGNORECASE):
        print("ERROR: SUPABASE_URL must look like https://<project-ref>.supabase.co", file=sys.stderr)
        return 2
    if not password:
        print("ERROR: a database password is required.", file=sys.stderr)
        return 2

    pg_url = supabase_postgres_url(url, password)
    if not pg_url:
        print("ERROR: could not build Postgres URL from those values.", file=sys.stderr)
        return 2

    print("\n→ Testing connection to Supabase Postgres…")
    ok, msg = asyncio.run(_try_connection(pg_url))
    print(f"  {msg}")
    if not ok:
        print(
            "\nDouble-check the password (Settings → Database → "
            "Database password → Reset password).",
            file=sys.stderr,
        )
        return 3

    if not args.no_migrate:
        print("\n→ Applying scripts/supabase_migration.sql…")
        ok, msg = asyncio.run(_run_migration(pg_url))
        print(f"  {msg}")
        if not ok:
            print(
                "\nIf the auto-migration failed, paste scripts/supabase_migration.sql "
                "into the Supabase SQL editor and run it manually.",
                file=sys.stderr,
            )
            # don't bail — user can finish manually

    save_settings_json(
        {
            "supabase_url": url,
            "supabase_anon_key": key,
            "supabase_db_password": password,
            # clear any explicit override so effective_database_url picks up Postgres
            "database_url": "",
        }
    )
    print(f"\n✓ Settings written to {SETTINGS_FILE}")
    print("✓ Lumora is now using Supabase. Restart the app (or it will pick this")
    print("  up on the next request) and you're done.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
