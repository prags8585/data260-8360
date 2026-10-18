#!/usr/bin/env python3


import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PORT, USER = 8261, "karthik_demo"


def start() -> subprocess.Popen:
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            requests.get(f"http://127.0.0.1:{PORT}/api/memory/{USER}", timeout=1)
            return proc
        except requests.RequestException:
            time.sleep(0.5)
    raise RuntimeError("server did not start")


def snapshot(label: str, proc: subprocess.Popen) -> tuple:
    mem = requests.get(f"http://127.0.0.1:{PORT}/api/memory/{USER}", timeout=30).json()
    agg = requests.get(f"http://127.0.0.1:{PORT}/api/aggregate/{USER}", timeout=30).json()
    out = (len(mem["last_messages"]), len(mem["episodic_facts"]), agg["total_messages"], bool(mem["latest_session_summary"]))
    print(f"{label}: pid={proc.pid} messages(last)={out[0]} episodic_facts={out[1]} total_messages={out[2]} session_summary={out[3]}")
    return out


def main() -> int:
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  persistence after restart")
    first = start()
    before = snapshot("MongoDB memory, server process #1", first)
    first.terminate()
    first.wait(timeout=10)
    print(f"server process #1 (pid {first.pid}) stopped")
    second = start()
    after = snapshot("MongoDB memory, server process #2", second)
    second.terminate()
    second.wait(timeout=10)
    print(f"identical after restart: {before == after}")
    code = ("from datetime import datetime, timezone; from pathlib import Path; import file_memory as fm; "
            "t = fm.load_memory_md(Path('MEMORY.md')); "
            "print('file memory, new interpreter:', fm.memory_health_report(t, datetime.now(timezone.utc)))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    print(out.stdout.strip() or out.stderr.strip())
    return 0 if before == after else 1


if __name__ == "__main__":
    sys.exit(main())
