#!/usr/bin/env python3
"""Pinterest manual login - opens browser and waits for user to log in"""
import json
import sys
import time
from pathlib import Path

CREDENTIALS_DIR = Path(__file__).parents[4] / "config" / "credentials"
COOKIE_FILE = CREDENTIALS_DIR / "pinterest-cookies.json"

WAIT_SECONDS = 90  # seconds to wait for user to log in


def manual_login_playwright():
    from playwright.sync_api import sync_playwright

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        print("Opening Pinterest login page...")
        page.goto("https://www.pinterest.com/login/", wait_until="domcontentloaded", timeout=30000)
        print(f"[OK] Browser opened. Please log in to Pinterest.")
        print(f"     Waiting {WAIT_SECONDS} seconds for you to complete login...")
        print()

        for i in range(WAIT_SECONDS, 0, -10):
            print(f"  {i} seconds remaining...")
            time.sleep(10)

        print()
        print("Capturing cookies...")
        cookies = context.cookies()
    finally:
        browser.close()
        pw.stop()

    auth_ok = any(c.get("name") == "_auth" and c.get("value") == "1" for c in cookies)

    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)

    print(f"[OK] Saved {len(cookies)} cookies -> {COOKIE_FILE}")
    print(f"     Auth status: {'SUCCESS' if auth_ok else 'FAILED (not logged in?)'}")

    if not auth_ok:
        print("[WARN] Login may not have completed. Try running again and log in faster.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        manual_login_playwright()
    except ImportError:
        print("[ERROR] playwright not installed.")
        print("Run: python -m pip install playwright && playwright install chromium")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
