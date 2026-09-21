#!/usr/bin/env python3
"""One-off script: drives the plain-HTTP screenshot instance (port 8261,
SESSION_HTTPS_ONLY=false) through the full auth flow with Playwright and
saves a screenshot per route/state to reports/hw03/assets/. Not part of
the graded app -- a report-generation helper only."""

from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8261"
OUT = Path(__file__).resolve().parent.parent / "reports/hw03/assets"
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 900, "height": 700})

    page.goto(f"{BASE}/")
    page.screenshot(path=OUT / "home_logged_out.png")

    page.goto(f"{BASE}/login")
    page.screenshot(path=OUT / "login_page.png")

    page.fill("#username", "karthik")
    page.fill("#password", "wrongpassword")
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=OUT / "login_invalid_alert.png")

    page.fill("#username", "karthik")
    page.fill("#password", "data260")
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=OUT / "dashboard.png")

    page.goto(f"{BASE}/")
    page.screenshot(path=OUT / "home_logged_in.png")

    page.goto(f"{BASE}/logout")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=OUT / "home_after_logout.png")

    page.goto(f"{BASE}/dashboard")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=OUT / "dashboard_blocked_when_logged_out.png")

    browser.close()

print("Saved screenshots to", OUT)
for f in sorted(OUT.glob("*.png")):
    print(" -", f.name, f.stat().st_size, "bytes")
