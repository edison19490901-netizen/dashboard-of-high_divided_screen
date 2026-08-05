# -*- coding: utf-8 -*-
"""
XHS Dashboard Screenshot Template — reusable for any project.

USAGE:
  1. Copy this file to your project as `screenshot_xhs.py`
  2. Fill in the SHOTS list below (one dict per screenshot)
  3. Run: python screenshot_xhs.py

Each shot dict:
  {
    "name": "01_cover.png",        # output filename
    "desc": "Cover - card grid",    # human-readable description
    "full_page": True,              # True = full page, False = viewport only
    "viewport": (750, 1334),       # (width, height) or None to keep current
    "setup": lambda page: None,     # optional: actions before screenshot
  }
"""

import http.server
import socketserver
import threading
import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

# ─── CONFIG: customize these ──────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
TARGET_HTML = "dashboard.html"        # the HTML file to screenshot
OUTPUT_DIR = BASE_DIR / "xhs_images"  # where screenshots go
PORT = 8765
DEVICE_SCALE = 2                      # 2x for crisp images

# ─── SHOTS: define your screenshots here ──────────────────────
# Each entry: (name, desc, full_page, viewport, setup_fn)
# viewport=None means use the DEFAULT_VW x DEFAULT_VH below
DEFAULT_VW = 750      # Xiaohongshu optimal width
DEFAULT_VH = 1334

SHOTS = [
    # --- EDIT BELOW: replace with your own shots ---
    {
        "name": "01_cover.png",
        "desc": "Cover - default view",
        "full_page": True,
        "viewport": None,
        "setup": lambda page: None,
    },
    {
        "name": "02_closeup.png",
        "desc": "Feature closeup - first screen",
        "full_page": False,
        "viewport": (750, 900),
        "setup": lambda page: None,
    },
    # --- EDIT ABOVE ---
]
# ──────────────────────────────────────────────────────────────


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)


def start_server():
    server = socketserver.TCPServer(("", PORT), Handler)
    server.timeout = 1
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def snap(page, name, full_page):
    path = str(OUTPUT_DIR / name)
    page.screenshot(path=path, full_page=full_page)
    print(f"  [OK] {name}")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    server = start_server()
    url = f"http://localhost:{PORT}/{TARGET_HTML}"
    print(f"Server: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": DEFAULT_VW, "height": DEFAULT_VH},
            device_scale_factor=DEVICE_SCALE,
        )
        page = ctx.new_page()

        for i, shot in enumerate(SHOTS):
            name = shot["name"]
            desc = shot.get("desc", name)
            full_page = shot.get("full_page", True)
            vp = shot.get("viewport") or (DEFAULT_VW, DEFAULT_VH)
            setup_fn = shot.get("setup", lambda p: None)

            print(f"\n[{i+1}/{len(SHOTS)}] {desc}")

            # Apply viewport
            page.set_viewport_size({"width": vp[0], "height": vp[1]})

            # Navigate fresh for each shot (isolated state)
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(2000)

            # Run custom setup (click, fill, sort, etc.)
            try:
                setup_fn(page)
                page.wait_for_timeout(500)
            except Exception as e:
                print(f"  [WARN] setup failed: {e}")

            snap(page, name, full_page)

        browser.close()

    server.shutdown()
    print(f"\nDone! {len(SHOTS)} images -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
