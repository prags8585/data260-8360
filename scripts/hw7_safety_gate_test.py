#!/usr/bin/env python3

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import file_tools as ft  # noqa: E402

SHOULD_PASS = ["ls -la", "cat notes.txt", "grep -n DEBUG app.py", "git status", "echo hello world"]
SHOULD_BLOCK = [
    "rm -fr /tmp/build",                 # recursive deletion (flags reordered)
    "sudo ls /root",                     # privilege escalation hidden behind a listing command
    "chmod 777 notes.txt",               # permission change
    "cat /dev/zero > /dev/sda",          # raw-device write via redirection, starts with an allow-listed command
    "sort -o /etc/hosts notes.txt",      # write to a root path through an allow-listed command's own output flag
]


def run(label: str = "final") -> int:
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  safety gate test ({label}); SAFE_PREFIXES has {len(ft.SAFE_PREFIXES)} entries")
    rows, false_allows, false_blocks = [], [], []
    for expected, commands in (("pass", SHOULD_PASS), ("block", SHOULD_BLOCK)):
        for command in commands:
            decision = ft.confirm_bash(command)
            destructive = ft.is_destructive(command)
            allowed = decision["allowed"]
            verdict = "ok"
            if expected == "block" and allowed:
                verdict = "FALSE ALLOW"
                false_allows.append(command)
            elif expected == "pass" and not allowed:
                verdict = "FALSE BLOCK"
                false_blocks.append(command)
            rows.append({"command": command, "expected": expected, "is_destructive": destructive, "allowed": allowed,
                         "reason": decision["reason"], "verdict": verdict})
            print(f"  expect {expected:5} | {command:34} | destructive={destructive!s:5} | {'ALLOW' if allowed else 'BLOCK'} | {decision['reason']} | {verdict}")
    passed = sum(r["verdict"] == "ok" for r in rows)
    print(f"\n{passed}/10 correct; false allows: {false_allows or 'none'}; false blocks: {false_blocks or 'none'}")
    out = ROOT / f"reports/hw07/raw/safety_gate_results_{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"label": label, "results": rows, "false_allows": false_allows, "false_blocks": false_blocks, "correct": passed}, indent=2))
    return 0 if not false_allows and not false_blocks else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "final"))
