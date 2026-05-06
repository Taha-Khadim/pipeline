#!/usr/bin/env bash
# Build a .deb package of Lumora Code — Client Pipeline for Ubuntu / Debian.
#
# Usage (from project root):
#   bash build/build-deb.sh
#
# Output:
#   build/dist/lumora-pipeline_<version>_amd64.deb
#
# Requires: python3.10+, dpkg-deb, fakeroot, pyinstaller (in venv).
#
# Optional bundled defaults (baked into the binary):
#   LUMORA_BUNDLED_DATABASE_URL     full Postgres URL (default: built-in Supabase pooler)
#   LUMORA_BUNDLED_SUPABASE_URL     Supabase project URL (REST API base)
#   LUMORA_BUNDLED_SUPABASE_KEY     anon/publishable key
#   LUMORA_BUNDLED_DB_PASSWORD      Supabase DB password (only needed if you let the
#                                   app derive the URL instead of providing DATABASE_URL)
#   LUMORA_BUNDLED_GOOGLE_API_KEY   pre-fill Gemini key

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${VERSION:-1.0.4}"
ARCH="${ARCH:-amd64}"
PKG_NAME="lumora-pipeline"
DIST="$ROOT/build/dist"
STAGING="$ROOT/build/.deb-staging-$VERSION"
PYI_OUT="$ROOT/build/dist-pyinstaller"

echo "==> Building $PKG_NAME $VERSION ($ARCH)"

if [[ ! -d "$ROOT/venv" ]]; then
  echo "venv not found. Create one and install requirements first:"
  echo "  python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt pyinstaller"
  exit 1
fi
# shellcheck disable=SC1091
source "$ROOT/venv/bin/activate"

echo "==> Installing build deps in venv"
pip install --quiet --upgrade pip
pip install --quiet --upgrade pyinstaller

# ---------------------------------------------------------------------------
#  Bake bundled defaults into app/_bundled_defaults.py before PyInstaller
#  reads it. Restored on EXIT so re-running this script (or running from
#  source after) doesn't pin secrets into the dev tree.
#
#  build/_bake_defaults.py reads its values from LUMORA_BUNDLED_* env vars
#  and falls back to the public Supabase pooler URL + publishable key, so
#  by default the produced artifact is fully self-contained.
# ---------------------------------------------------------------------------
DEFAULTS_FILE="$ROOT/app/_bundled_defaults.py"
DEFAULTS_BACKUP="$DEFAULTS_FILE.bak.$$"
cp "$DEFAULTS_FILE" "$DEFAULTS_BACKUP"
trap 'mv "$DEFAULTS_BACKUP" "$DEFAULTS_FILE" 2>/dev/null || true' EXIT
echo "==> Embedding bundled defaults"
python "$ROOT/build/_bake_defaults.py"

echo "==> Running PyInstaller"
rm -rf "$PYI_OUT" build/build "$ROOT/dist"
pyinstaller lumora.spec --noconfirm --distpath "$PYI_OUT" --workpath "$ROOT/build/build" >/dev/null
BUNDLE="$PYI_OUT/$PKG_NAME"
if [[ ! -d "$BUNDLE" ]]; then
  echo "PyInstaller bundle missing at $BUNDLE"; exit 1
fi

echo "==> Bundling Playwright Chromium"
mkdir -p "$BUNDLE/ms-playwright"
PLAYWRIGHT_BROWSERS_PATH="$BUNDLE/ms-playwright" \
  python -m playwright install chromium >/dev/null

echo "==> Staging .deb tree"
rm -rf "$STAGING"
mkdir -p "$STAGING/DEBIAN" \
         "$STAGING/opt/$PKG_NAME" \
         "$STAGING/usr/bin" \
         "$STAGING/usr/share/applications" \
         "$STAGING/usr/share/icons/hicolor/scalable/apps"

cp -r "$BUNDLE/." "$STAGING/opt/$PKG_NAME/"
cp "$ROOT/favicon.svg" "$STAGING/usr/share/icons/hicolor/scalable/apps/$PKG_NAME.svg"

cat >"$STAGING/usr/bin/$PKG_NAME" <<'WRAPPER'
#!/usr/bin/env bash
exec /opt/lumora-pipeline/lumora-pipeline "$@"
WRAPPER
chmod +x "$STAGING/usr/bin/$PKG_NAME"

cat >"$STAGING/usr/share/applications/$PKG_NAME.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Lumora Code — Client Pipeline
Comment=Find clients, manage pipeline, generate outreach
Exec=$PKG_NAME
Icon=$PKG_NAME
Terminal=false
Categories=Office;ProjectManagement;
DESKTOP

INSTALLED_SIZE_KB=$(du -sk "$STAGING/opt" | awk '{print $1}')

cat >"$STAGING/DEBIAN/control" <<CONTROL
Package: $PKG_NAME
Version: $VERSION
Section: web
Priority: optional
Architecture: $ARCH
Installed-Size: $INSTALLED_SIZE_KB
Maintainer: Lumora Code <hello@lumoracode.com>
Depends: libnss3, libatk1.0-0, libatk-bridge2.0-0, libdrm2, libxkbcommon0, libxcomposite1, libxdamage1, libxfixes3, libxrandr2, libgbm1, libpango-1.0-0, libcairo2, libasound2 | libasound2t64
Description: Local-first client hunting + pipeline tool
 Discover small businesses across Google Maps and Bing Local,
 enrich their contact info, and generate AI-personalized outreach
 (cold emails, call scripts, DMs). Runs entirely on your machine.
CONTROL

cat >"$STAGING/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
fi
exit 0
POSTINST
chmod 755 "$STAGING/DEBIAN/postinst"

echo "==> Building .deb"
mkdir -p "$DIST"
DEB_FILE="$DIST/${PKG_NAME}_${VERSION}_${ARCH}.deb"
fakeroot dpkg-deb --build "$STAGING" "$DEB_FILE" >/dev/null

echo
echo "✓ Built: $DEB_FILE"
echo "  Size:  $(du -h "$DEB_FILE" | awk '{print $1}')"
echo
echo "Install with:"
echo "  sudo apt install -y \"$DEB_FILE\""
echo "Or:"
echo "  sudo dpkg -i \"$DEB_FILE\" && sudo apt -f install"
