"""
Async DB engine — always backed by Supabase Postgres (asyncpg).

The connection URL is resolved lazily by
`app.config.Settings.effective_database_url` so the user can change it
from the in-app Settings page without restarting the server.
"""

from __future__ import annotations

import logging
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

log = logging.getLogger(__name__)


def _ssl_context() -> ssl.SSLContext:
    """Permissive SSL context for Supabase poolers (self-signed chain)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_engine():
    settings = get_settings()
    url = settings.effective_database_url

    connect_args: dict = {
        "ssl": _ssl_context(),
        # Keep statement caching off — required for the transaction pooler
        # (port 6543) and harmless for the session pooler / direct hosts.
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
    log.info("Database backend: Supabase Postgres (%s)", _redact(url))

    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=900,
        connect_args=connect_args,
    )


def _redact(url: str) -> str:
    """Hide the password segment in log output."""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        if parts.username and parts.password:
            netloc = f"{parts.username}:***@{parts.hostname}"
            if parts.port:
                netloc += f":{parts.port}"
            return urlunsplit(parts._replace(netloc=netloc))
    except Exception:
        pass
    return url


engine = _build_engine()
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    """Verify connectivity at startup. The schema itself is provisioned by
    `scripts/supabase_migration.sql` (idempotent), so we don't run
    `create_all` here — that would only matter for a brand-new project
    and would duplicate the migration's enums/triggers.

    A failure here is logged but does NOT raise — the user can still open
    the Settings page and fix the connection string from the UI. Any DB
    requests until then will surface their own error.
    """
    import asyncio

    from sqlalchemy import text

    async def _ping() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_ping(), timeout=10)
        log.info("✓ Connected to Supabase Postgres")
    except Exception as exc:
        log.warning(
            "Could not reach Supabase on startup: %s. "
            "Open the Settings page to fix the connection.",
            exc,
        )


async def reset_engine() -> None:
    """Dispose the engine and rebuild it from current settings.

    Called from the Settings page after the user changes the connection
    URL or DB password so the new credentials take effect immediately.
    """
    global engine, async_session
    try:
        await engine.dispose()
    except Exception:
        pass
    get_settings.cache_clear()
    engine = _build_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)
