
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("file_memory")

ROOT = Path(__file__).resolve().parent
AGENT_PATH = ROOT / "AGENT.md"
MEMORY_PATH = ROOT / "MEMORY.md"

MAX_LINES = 40
MAX_AGE = timedelta(hours=24)
STAMP_RE = re.compile(r"<!--\s*last-consolidated:\s*(\S+?)\s*-->")
FACT_RE = re.compile(r"^- \((\d{4}-\d{2}-\d{2})\) ([a-z0-9_]+): (.+?)(?: \(x(\d+)\))?$")
QUALIFIERS = ("temporary", "test container", "only", "until", "for now", "trial")
BASE_PROMPT = "You are a helpful academic-planning assistant. Use the project instructions and the remembered facts below."

HELP_TEXT = """Available commands:
/memory   show the current file-based memory (AGENT.md + MEMORY.md)
/compact  consolidate MEMORY.md (merge duplicates, resolve contradictions) and report line counts before and after
/dream    extract durable facts from the recent conversation and add them to MEMORY.md
/help     show this help"""


# --- loading and prompt construction ------------------------------------------------

def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_agent_md(path: Path = AGENT_PATH) -> str:
    return load_text(path)


def load_memory_md(path: Path = MEMORY_PATH) -> str:
    return load_text(path)


def build_system_prompt(agent_text: str, memory_text: str, base: str = BASE_PROMPT) -> str:
    return f"{base}\n\n## Project instructions (AGENT.md)\n{agent_text.strip()}\n\n## Remembered facts (MEMORY.md)\n{memory_text.strip()}"


# --- consolidation checks -----------------------------------------------------------------

def read_last_consolidated(memory_text: str) -> datetime | None:
    match = STAMP_RE.search(memory_text)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("<!--") and stripped.endswith("-->")


def count_memory_lines(memory_text: str) -> int:
    """Non-empty, non-comment lines."""
    return sum(1 for line in memory_text.splitlines() if line.strip() and not is_comment(line))


def needs_consolidation(memory_text: str, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    lines = count_memory_lines(memory_text)
    if lines > MAX_LINES:
        return True, f"{lines} non-empty, non-comment lines (> {MAX_LINES})"
    stamp = read_last_consolidated(memory_text)
    if stamp is None:
        return True, "no last-consolidated timestamp recorded"
    age = now - stamp
    if age > MAX_AGE:
        return True, f"last consolidated {age.total_seconds() / 3600:.1f} h ago (> 24 h)"
    return False, f"{lines} lines, consolidated {age.total_seconds() / 3600:.1f} h ago"


def memory_health_report(memory_text: str, now: datetime) -> dict:
    stamp = read_last_consolidated(memory_text)
    required, reason = needs_consolidation(memory_text, now)
    return {
        "entries": count_memory_lines(memory_text),
        "total_lines": len(memory_text.splitlines()),
        "last_consolidated": stamp.isoformat() if stamp else None,
        "age_hours": round((now - stamp).total_seconds() / 3600, 1) if stamp else None,
        "needs_consolidation": required,
        "reason": reason,
    }


# --- consolidation --------------------------------------------------------------------------

@dataclass
class Fact:
    date: str
    topic: str
    value: str
    count: int = 1


@dataclass
class ConsolidationReport:
    lines_before: int
    lines_after: int
    entries_before: int
    entries_after: int
    duplicates_merged: int = 0
    contradictions: list[dict] = field(default_factory=list)
    unparsed_kept: int = 0


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


AUDIT_HEADING = "## Resolved contradictions"


def parse_facts(memory_text: str) -> tuple[list[Fact], list[str], list[str]]:
    """Returns (facts, other free-text lines, audit lines carried over from a previous consolidation)."""
    facts, other, audit = [], [], []
    in_audit = False
    for line in memory_text.splitlines():
        if line.startswith("## "):
            in_audit = line.startswith(AUDIT_HEADING)
            continue
        if in_audit:
            if line.strip():
                audit.append(line.rstrip())
            continue
        match = FACT_RE.match(line.strip())
        if match:
            facts.append(Fact(match.group(1), match.group(2), match.group(3).strip(), int(match.group(4) or 1)))
        elif line.strip() and not is_comment(line) and not line.startswith("#"):
            other.append(line.rstrip())
    return facts, other, audit


def merge_duplicates(facts: list[Fact]) -> tuple[list[Fact], int]:
    merged: dict[tuple[str, str], Fact] = {}
    for fact in facts:
        key = (fact.topic, _norm(fact.value))
        if key in merged:
            kept = merged[key]
            kept.count += fact.count
            kept.date = max(kept.date, fact.date)
        else:
            merged[key] = Fact(fact.date, fact.topic, fact.value, fact.count)
    return list(merged.values()), len(facts) - len(merged)


def resolve_contradictions(facts: list[Fact]) -> tuple[list[Fact], list[dict]]:
    """Same topic with different values: the most recent date wins. Older values
    are never dropped silently -- each is returned as a record for the audit section."""
    by_topic: dict[str, list[Fact]] = {}
    for fact in facts:
        by_topic.setdefault(fact.topic, []).append(fact)
    survivors, records = [], []
    for topic, group in by_topic.items():
        group.sort(key=lambda f: f.date)
        winner = group[-1]
        survivors.append(winner)
        for loser in group[:-1]:
            suspect = any(q in winner.value.lower() for q in QUALIFIERS)
            records.append({"topic": topic, "kept": winner.value, "kept_date": winner.date,
                            "superseded": loser.value, "superseded_date": loser.date,
                            "rule": "most recent entry wins", "needs_review": suspect})
    return survivors, records


def render(facts: list[Fact], records: list[dict], other: list[str], now: datetime,
           carried_audit: list[str] | None = None) -> str:
    out = ["# MEMORY.md", f"<!-- last-consolidated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')} -->",
           "<!-- Format: - (YYYY-MM-DD) topic: value  | consolidated by file_memory.consolidate() -->", "", "## Facts"]
    for fact in sorted(facts, key=lambda f: f.topic):
        suffix = f" (x{fact.count})" if fact.count > 1 else ""
        out.append(f"- ({fact.date}) {fact.topic}: {fact.value}{suffix}")
    out += [line for line in other]
    audit = list(carried_audit or [])
    for r in records:
        flag = " [NEEDS REVIEW: newer value looks qualified]" if r["needs_review"] else ""
        line = (f"- {r['topic']}: kept \"{r['kept']}\" ({r['kept_date']}); superseded \"{r['superseded']}\" "
                f"({r['superseded_date']}){flag}")
        if line not in audit:
            audit.append(line)
    if audit:
        out += ["", f"{AUDIT_HEADING} (older values kept for audit)"] + audit
    return "\n".join(out) + "\n"


def consolidate(memory_text: str, now: datetime | None = None) -> tuple[str, ConsolidationReport]:
    now = now or datetime.now(timezone.utc)
    facts, other, carried = parse_facts(memory_text)
    merged, dup_count = merge_duplicates(facts)
    survivors, records = resolve_contradictions(merged)
    new_text = render(survivors, records, sorted(set(other)), now, carried)
    report = ConsolidationReport(
        lines_before=len(memory_text.splitlines()), lines_after=len(new_text.splitlines()),
        entries_before=count_memory_lines(memory_text), entries_after=count_memory_lines(new_text),
        duplicates_merged=dup_count, contradictions=records, unparsed_kept=len(set(other)))
    return new_text, report


# --- commands ------------------------------------------------------------------------------------

def cmd_help() -> str:
    return HELP_TEXT


def cmd_memory(agent_path: Path = AGENT_PATH, memory_path: Path = MEMORY_PATH) -> str:
    agent, memory = load_agent_md(agent_path), load_memory_md(memory_path)
    health = memory_health_report(memory, datetime.now(timezone.utc))
    return (f"--- AGENT.md ({len(agent.splitlines())} lines) ---\n{agent.strip()}\n\n"
            f"--- MEMORY.md ({health['entries']} entries, {health['total_lines']} lines, "
            f"last consolidated {health['last_consolidated']}) ---\n{memory.strip()}")


def cmd_compact(memory_path: Path = MEMORY_PATH, now: datetime | None = None) -> str:
    text = load_memory_md(memory_path)
    if not text.strip():
        return "MEMORY.md is empty; nothing to compact."
    new_text, rep = consolidate(text, now)
    backup = memory_path.with_name(memory_path.name + ".bak")
    shutil.copyfile(memory_path, backup)                      # AGENT.md: never overwrite without a backup
    memory_path.write_text(new_text, encoding="utf-8")
    flagged = sum(1 for r in rep.contradictions if r["needs_review"])
    return (f"/compact: MEMORY.md consolidated.\n"
            f"  lines   : {rep.lines_before} -> {rep.lines_after}\n"
            f"  entries : {rep.entries_before} -> {rep.entries_after} (non-empty, non-comment)\n"
            f"  merged {rep.duplicates_merged} duplicate fact(s); resolved {len(rep.contradictions)} contradiction(s) "
            f"({flagged} flagged NEEDS REVIEW); backup written to {backup.name}")


DREAM_SYSTEM = (
    "From the conversation below, list durable long-term facts about the user (names, preferences, plans, constraints). "
    'Return JSON only: {"facts": [{"topic": "<snake_case_key>", "value": "<short value>"}]} with at most 5 facts. '
    'If there are none return {"facts": []}.'
)


def parse_dream(raw: str) -> list[tuple[str, str]]:
    try:
        items = json.loads(raw).get("facts", [])
    except (ValueError, AttributeError):
        return []
    facts = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("topic"), str) and isinstance(item.get("value"), str):
            topic = re.sub(r"[^a-z0-9_]+", "_", item["topic"].lower()).strip("_")
            if topic and item["value"].strip():
                facts.append((topic, item["value"].strip()))
    return facts[:5]


def cmd_dream(llm, history: list[tuple[str, str]], memory_path: Path = MEMORY_PATH, today: str | None = None) -> str:
    if not history:
        return "/dream: no recent conversation to learn from."
    transcript = "\n".join(f"{role}: {text}" for role, text in history[-12:])
    raw = llm.complete([("system", DREAM_SYSTEM), ("user", transcript)]).content
    found = parse_dream(raw)
    existing = load_memory_md(memory_path)
    stamp = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    added = []
    for topic, value in found:
        line = f"- ({stamp}) {topic}: {value}"
        if _norm(value) not in _norm(existing) or f"{topic}:" not in existing:
            added.append(line)
    if added:
        with open(memory_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(added) + "\n")
    shown = "\n".join(added) if added else "(nothing new)"
    return f"/dream: {len(found)} candidate fact(s), {len(added)} added to MEMORY.md\n{shown}"


def handle_command(text: str, llm=None, history=None, agent_path: Path = AGENT_PATH,
                   memory_path: Path = MEMORY_PATH) -> str | None:
    """Returns the command output, or None when `text` is not a command."""
    command = text.strip().split()[0].lower() if text.strip().startswith("/") else None
    if command == "/help":
        return cmd_help()
    if command == "/memory":
        return cmd_memory(agent_path, memory_path)
    if command == "/compact":
        return cmd_compact(memory_path)
    if command == "/dream":
        return cmd_dream(llm, history or [], memory_path)
    if command:
        return f"Unknown command {command}. Type /help for the list."
    return None
