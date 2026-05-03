"""
Lumora Code — Client Pipeline launcher.

Starts the FastAPI server on a free local port and opens the user's default
browser to the dashboard. Used as the entry point for desktop installers
(`.deb` on Linux, `.exe` on Windows).

Behavior:
  * Picks a port (default 8765, falls back to a free one if taken).
  * Spawns uvicorn in-process.
  * Opens http://127.0.0.1:<port>/ in the default browser after a short delay.
  * Keeps running until Ctrl+C / window close.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import webbrowser

DEFAULT_PORT = 8765
HOST = "127.0.0.1"


def _is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _pick_port(preferred: int) -> int:
    if _is_port_free(HOST, preferred):
        return preferred
    for p in range(preferred + 1, preferred + 50):
        if _is_port_free(HOST, p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _open_browser_when_ready(url: str, delay: float = 2.0) -> None:
    def go():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=go, daemon=True).start()


def _frozen_setup() -> None:
    """When running as a PyInstaller bundle, point Playwright at the bundled
    browsers and ensure asyncio uses the right loop on Windows."""
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        # Bundled Playwright browsers — only use if present.
        bundled = os.path.join(bundle_dir, "ms-playwright")
        if os.path.isdir(bundled):
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", bundled)
        # Tell the app not to try `playwright install` in frozen mode.
        os.environ.setdefault("LUMORA_SKIP_PLAYWRIGHT_INSTALL", "1")


def main() -> int:
    _frozen_setup()

    parser = argparse.ArgumentParser(prog="lumora-pipeline")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open a browser window automatically.")
    parser.add_argument("--data-dir", default=None,
                        help="Directory where settings + DB are stored.")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["LUMORA_DATA_DIR"] = args.data_dir

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    port = _pick_port(args.port)
    url = f"http://{args.host}:{port}/"

    print("┌────────────────────────────────────────────┐")
    print("│  Lumora Code — Client Pipeline              │")
    print(f"│  Open your browser at: {url:<19}│")
    print("│  (close this window to stop the app)        │")
    print("└────────────────────────────────────────────┘")

    if not args.no_browser:
        _open_browser_when_ready(url)

    import uvicorn
    from app.main import app
    uvicorn.run(app, host=args.host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
