#!/usr/bin/env python3


import json
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8260"
USER, SESSION = "karthik_demo", "demo-session"
OUT = Path(__file__).resolve().parent.parent / "reports/hw06/raw"

MESSAGES = [
    "Hi! I'm Karthik, a graduate student in the MS Data Analytics program.",
    "I'm taking DATA-260 this semester and it is my favorite course so far.",
    "My academic advisor is Dr. Priya Nair.",
    "I live in San Jose and I commute by Caltrain.",
    "I prefer evening classes because I have a morning internship.",
    "Which courses should I look at for a data engineering focus?",
    "I plan to graduate in December 2026.",
    "Can you remind me who my advisor is?",
    "I have a project demo next Friday for the memory homework.",
    "What was my favorite course again?",
    "Do I prefer morning or evening classes?",
    "Summarize what you know about me in two sentences.",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  chat page demo, user_id={USER} session_id={SESSION}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1240, "height": 780}, device_scale_factor=2)
        page.goto(f"{BASE}/static/chat.html?user_id={USER}&session_id={SESSION}")
        for i, text in enumerate(MESSAGES, 1):
            page.fill("#text", text)
            with page.expect_response(lambda r: r.url.endswith("/api/chat")) as resp:
                page.click("#send")
            data = resp.value.json()
            page.wait_for_function("!document.getElementById('send').disabled")
            u = data["usage"]
            print(f"[{i:2}] user: {text}\n     bot : {data['reply'][:110]}\n"
                  f"     memory: window={data['used']['short_term_count']} facts={len(data['used']['episodic_facts'])} "
                  f"prompt={u['prompt_tokens']} completion={u['completion_tokens']} latency={u['latency_ms']:.0f} ms")
        page.screenshot(path=str(OUT / "part2_chat_ui.png"))
        browser.close()

    memory = requests.get(f"{BASE}/api/memory/{USER}", timeout=30).json()
    aggregate = requests.get(f"{BASE}/api/aggregate/{USER}", timeout=30).json()
    (OUT / "part2_memory.json").write_text(json.dumps(memory, indent=2))
    (OUT / "part2_aggregate.json").write_text(json.dumps(aggregate, indent=2))
    print(f"\nGET /api/memory/{USER}: {len(memory['last_messages'])} messages, "
          f"session summary={'yes' if memory['latest_session_summary'] else 'no'}, "
          f"lifetime summary={'yes' if memory['latest_lifetime_summary'] else 'no'}, "
          f"{len(memory['episodic_facts'])} episodic facts")
    print(f"GET /api/aggregate/{USER}: daily={aggregate['daily_message_counts']} total={aggregate['total_messages']}")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
