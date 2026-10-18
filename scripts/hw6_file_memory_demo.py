#!/usr/bin/env python3


import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import file_memory as fm  # noqa: E402
from file_memory_agent import FileMemoryAgent  # noqa: E402
from src.model_client import ModelClient  # noqa: E402

OUT = ROOT / "reports/hw06/raw/memory_consolidation"
SCRATCH = OUT / "session"
# What is actually true for each contradictory topic (known when the file was written).
GROUND_TRUTH = {
    "theme": "light mode", "graduation": "December 2027", "advisor": "Dr. Marcus Lee",
    "database_port": "3306", "work_hours": "12 hours per week at the campus library",
}


def banner(text: str) -> None:
    print(f"\n{'=' * 8} {text} {'=' * 8}")


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    memory = SCRATCH / "MEMORY.md"
    agent_md = SCRATCH / "AGENT.md"
    shutil.copyfile(OUT / "MEMORY.original.md", memory)
    shutil.copyfile(ROOT / "AGENT.md", agent_md)
    agent = FileMemoryAgent(ModelClient("qwen3:8b", 0.0, num_predict=160), agent_md, memory)
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')} ===  file-based memory demo (scratch dir {SCRATCH.relative_to(ROOT)})")

    banner("/help")
    print(agent.reply("/help"))

    banner("/memory  (original)")
    print(agent.reply("/memory"))

    banner("consolidation check")
    required, reason = fm.needs_consolidation(fm.load_memory_md(memory))
    print(f"needs_consolidation -> {required}: {reason}")

    banner("/compact")
    print(agent.reply("/compact"))
    shutil.copyfile(memory, OUT / "MEMORY.consolidated.md")
    required, reason = fm.needs_consolidation(fm.load_memory_md(memory))
    print(f"needs_consolidation after /compact -> {required}: {reason}")

    banner("/memory  (consolidated)")
    print(agent.reply("/memory").split("--- MEMORY.md")[1].join(["--- MEMORY.md", ""]))

    banner("chat that relies on MEMORY.md in the system prompt")
    for question in ["Which port does my backend run on, and who is my academic advisor?",
                     "Which port is my database listening on?"]:
        print(f"user      : {question}")
        print(f"assistant : {agent.reply(question)}\n")

    banner("/dream")
    agent.history += [("user", "By the way, I switched my favorite course to DATA-260 and I now prefer afternoon lab sections."),
                      ("assistant", "Noted - DATA-260 as your favorite and afternoon labs.")]
    print(agent.reply("/dream"))

    banner("audit of the resolved contradictions (vs. what is actually true)")
    text = fm.load_text(OUT / "MEMORY.original.md")
    _, report = fm.consolidate(text, datetime.now(timezone.utc))
    audit = []
    for r in report.contradictions:
        truth = GROUND_TRUTH[r["topic"]]
        correct = r["kept"].lower().startswith(truth.lower().split(",")[0].split(" (")[0]) or truth.lower() in r["kept"].lower()
        audit.append({**r, "ground_truth": truth, "resolved_correctly": correct})
        mark = "CORRECT  " if correct else "INCORRECT"
        review = "flagged NEEDS REVIEW" if r["needs_review"] else "not flagged"
        print(f"  [{mark}] {r['topic']:<14} kept {r['kept']!r:<52} truth {truth!r}  ({review})")
    wrong = [a for a in audit if not a["resolved_correctly"]]
    flagged_wrong = [a for a in wrong if a["needs_review"]]
    print(f"\n{len(wrong)} of {len(audit)} contradictions resolved incorrectly by 'most recent wins'; "
          f"{len(flagged_wrong)} of those were flagged NEEDS REVIEW by the qualifier heuristic")

    (OUT / "consolidation_audit.json").write_text(json.dumps(
        {"lines_before": report.lines_before, "lines_after": report.lines_after, "entries_before": report.entries_before,
         "entries_after": report.entries_after, "duplicates_merged": report.duplicates_merged, "audit": audit}, indent=2))
    shutil.copyfile(OUT / "MEMORY.consolidated.md", ROOT / "MEMORY.md")      # repository MEMORY.md = consolidated version
    print(f"\nrepository MEMORY.md set to the consolidated version ({len(fm.load_memory_md(ROOT / 'MEMORY.md').splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
