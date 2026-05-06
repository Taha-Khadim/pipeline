# PyInstaller spec for Lumora Code — Client Pipeline.
#
# Builds a single-folder bundle (`dist/lumora-pipeline/`) with all Python
# deps + templates + static assets. The launcher is the entry point.
#
# Build:
#   pyinstaller lumora.spec --noconfirm
#
# After build, copy bundled Playwright browsers into the dist folder:
#   PLAYWRIGHT_BROWSERS_PATH=dist/lumora-pipeline/ms-playwright \
#       python -m playwright install chromium

# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

block_cipher = None
HERE = Path(os.path.abspath(SPECPATH))

datas = [
    (str(HERE / "app" / "templates"), "app/templates"),
    (str(HERE / "app" / "static"),    "app/static"),
    (str(HERE / "favicon.svg"),       "."),
    (str(HERE / "scripts" / "supabase_migration.sql"), "scripts"),
]

hiddenimports = [
    "asyncpg",
    "asyncpg.protocol",
    "asyncpg.protocol.protocol",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "google.generativeai",
    "google.ai.generativelanguage",
    "playwright.async_api",
    "playwright._impl._driver",
    "app.templating",
    "app.routers.dashboard",
    "app.routers.discover",
    "app.routers.leads",
    "app.routers.outreach",
    "app.routers.settings",
    "app.scrapers.google_maps",
    "app.scrapers.yelp",
    "app.scrapers.yellowpages",
    "app.scrapers.openstreetmap",
    "app.scrapers.contact_finder",
    "app.scrapers.website_analyzer",
    "app.ai._gemini",
    "app.ai.research_agent",
    "app.ai.outreach_gen",
    "app._bundled_defaults",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "numpy", "pandas",
        "PIL", "torch", "tensorflow", "scipy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lumora-pipeline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / "favicon.svg") if (HERE / "favicon.svg").exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="lumora-pipeline",
)
