#!/usr/bin/env python3


import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw07/raw"
BASE = "http://localhost:8260"
URL = "https://lyftbikes.com/pricing"
SCENARIOS = {"A": "scenario_A_membership_wins.csv", "B": "scenario_B_pay_per_use_wins.csv"}


def main() -> None:
    wanted = sys.argv[1:] or list(SCENARIOS)
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  UI acceptance runs {wanted} against {BASE}/static/bikeshare.html")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for key in wanted:
            page = browser.new_page(viewport={"width": 1300, "height": 900}, device_scale_factor=2)
            latest = {}
            page.on("response", lambda r: latest.update(job=r.json()) if "/api/bikeshare/jobs/" in r.url and r.ok else None)
            page.goto(f"{BASE}/static/bikeshare.html")
            page.set_input_files("#csv", str(RAW / "scenarios" / SCENARIOS[key]))
            page.fill("#url", URL)
            page.click("#run")
            print(f"[{key}] Run pressed for {SCENARIOS[key]}")
            page.wait_for_function("document.getElementById('status').textContent === 'Finished.' || document.getElementById('status').textContent.startsWith('Error')", timeout=900000)
            page.wait_for_timeout(500)
            job = latest["job"]
            (RAW / f"part4_scenario_{key}_result.json").write_text(json.dumps(job["result"], indent=2))
            page.screenshot(path=str(RAW / f"part4_ui_scenario_{key}.png"), full_page=True)
            r = job["result"]
            print(f"[{key}] decision={r.get('decision')!r} costs={r.get('costs')} metrics={r['metrics']} check={r.get('check')}")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
