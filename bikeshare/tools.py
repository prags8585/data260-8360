import ast
import csv
import hashlib
import io
import operator
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE_CSV = "uploaded.csv"
MAX_ROWS = 200
CALC_WHITELIST = re.compile(r"^[0-9+\-*/().\s]+$")

TOOL_SCHEMAS = {
    "csv_sql": {
        "type": "object", "properties": {"sql": {"type": "string", "description": "one read-only SELECT over the table `trips`"}},
        "required": ["sql"], "additionalProperties": False,
    },
    "policy_retriever": {
        "type": "object",
        "properties": {"url": {"type": "string"}, "query": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 10}},
        "required": ["url", "query"], "additionalProperties": False,
    },
    "calculator": {
        "type": "object",
        "properties": {"expression": {"type": "string", "pattern": r"^[0-9+\-*/().\s]+$"}, "units": {"type": "string"}},
        "required": ["expression"], "additionalProperties": False,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def envelope(success: bool, data=None, error: str | None = None, source: str | None = None) -> dict:
    out: dict = {"success": success, "ts": now_iso()}
    if data is not None:
        out["data"] = data
    if error is not None:
        out["error"] = error
    if source is not None:
        out["source"] = source
    return out


# --- csv_sql ----------------------------------------------------------------------------------

class TripStore:
    """The uploaded trip CSV loaded into an in-memory SQLite table `trips` with derived columns:
    duration_min, is_ebike, week_start (Monday), month (YYYY-MM)."""

    DERIVED = ("duration_min", "is_ebike", "week_start", "month")

    def __init__(self, csv_text: str):
        reader = csv.DictReader(io.StringIO(csv_text))
        self.columns = list(reader.fieldnames or [])
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        cols = ", ".join(f'"{c}" TEXT' for c in self.columns)
        self.con.execute(f"CREATE TABLE trips ({cols}, duration_min REAL, is_ebike INTEGER, week_start TEXT, month TEXT)")
        self.skipped_rows = 0
        self.mutated = False  # set when a non-SELECT statement executed (only possible when the read-only contract is off)
        marks = ", ".join("?" for _ in self.columns) + ", ?, ?, ?, ?"
        for row in reader:
            try:
                start = datetime.fromisoformat(row["started_at"])
                end = datetime.fromisoformat(row["ended_at"])
            except (KeyError, ValueError):
                self.skipped_rows += 1
                continue
            monday = start.date().toordinal() - start.weekday()
            self.con.execute(f"INSERT INTO trips VALUES ({marks})", [row.get(c) for c in self.columns] + [
                round((end - start).total_seconds() / 60, 2), 1 if "electric" in (row.get("rideable_type") or "") else 0,
                datetime.fromordinal(monday).strftime("%Y-%m-%d"), start.strftime("%Y-%m"),
            ])
        self.con.commit()
        self.row_count = self.con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]

    @classmethod
    def from_path(cls, path: str | Path) -> "TripStore":
        return cls(Path(path).read_text(encoding="utf-8"))


_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _readonly_violation(sql: str) -> str | None:
    """Why `sql` is not a single read-only SELECT, or None. Comments and string literals are stripped first."""
    stripped = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    code = re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", stripped)
    if ";" in code.strip().rstrip(";"):
        return "only one statement is allowed"
    if not re.match(r"^\s*(select|with)\b", code, re.I):
        return "only SELECT statements are allowed"
    return None


def csv_sql(store: TripStore, sql: str, enforce_readonly: bool = True) -> dict:
    """Run a query over the uploaded trips. With enforce_readonly (the default) the statement must be ONE SELECT and SQLite's
    authorizer additionally refuses everything except reads, so even a clever statement cannot modify or attach anything."""
    if not isinstance(sql, str) or not sql.strip():
        return envelope(False, error="sql must be a non-empty string", source=SOURCE_CSV)
    if enforce_readonly:
        problem = _readonly_violation(sql)
        if problem:
            return envelope(False, error=f"read-only contract violated: {problem}", source=SOURCE_CSV)
        store.con.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY)
    else:
        store.con.set_authorizer(None)
    try:
        cur = store.con.execute(sql.strip().rstrip(";"))
        if cur.description is None:  # a non-SELECT statement ran (only possible without enforcement)
            store.con.commit()
            store.mutated = True
            return envelope(True, {"rows": [], "row_count": cur.rowcount, "source": SOURCE_CSV}, source=SOURCE_CSV)
        names = [d[0] for d in cur.description]
        fetched = cur.fetchmany(MAX_ROWS + 1)
        rows = [dict(zip(names, r)) for r in fetched[:MAX_ROWS]]
        data = {"rows": rows, "row_count": len(rows), "source": SOURCE_CSV}
        if len(fetched) > MAX_ROWS:
            data["truncated"] = True
        return envelope(True, data, source=SOURCE_CSV)
    except sqlite3.Error as exc:
        return envelope(False, error=f"sql error: {exc}", source=SOURCE_CSV)
    finally:
        store.con.set_authorizer(None)


# --- policy_retriever -------------------------------------------------------------------------

def fetch_page(url: str, timeout: int = 25) -> tuple[str, str]:
    """Returns (raw html, how it was fetched). file:// URLs and local paths are read from disk (local fixtures)."""
    if url.startswith("file://") or (not url.startswith("http") and Path(url).exists()):
        return Path(url.removeprefix("file://")).read_text(encoding="utf-8"), "local file"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (DATA260 HW7 student project)"}, timeout=timeout)
    response.raise_for_status()
    return response.text, f"HTTP {response.status_code}"


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "head"]):
        tag.decompose()
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9$.]+", text.lower()))


_CTA = re.compile(r"^(get |join|download|log in|sign|skip|explore|compare|learn)", re.I)
_BARE_PRICE = re.compile(r"^\$\d[\d.,]*(/\w+)?$")


def _is_heading(lines: list[str], i: int) -> bool:
    """A short label line (e.g. 'Month pass') directly followed by a bare price such as '$29/month': the start of a plan block."""
    line = lines[i]
    if len(line) > 40 or line.startswith("$") or _CTA.match(line):
        return False
    return any(_BARE_PRICE.match(ln) for ln in lines[i + 1:i + 3])


def plan_names(text: str) -> list[str]:
    """Plan headings of the page (lines such as 'Month pass' that are directly followed by a bare price)."""
    lines = text.split("\n")
    return sorted({lines[i] for i in range(len(lines)) if _is_heading(lines, i)}, key=len, reverse=True)


def _blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    starts = [i for i in range(len(lines)) if _is_heading(lines, i)]
    if not starts:
        return []
    cuts = starts + [len(lines)]
    return [(s, lines[s:e]) for s, e in zip(cuts, cuts[1:])]


def _annotate_columns(blocks: list[tuple[int, list[str]]]) -> list[tuple[int, str]]:
    """Flattening the page's comparison table loses its columns: every plan block repeats a list of N rules, one per plan, in plan order.
    When N equals the number of plan blocks that carry such lists, each rule is tagged with its plan in square brackets
    (the tags are the retriever's, not the page's; the citation check ignores them)."""
    carriers = [(i, blk) for i, blk in blocks if any(ln.lower().endswith("prices") for ln in blk)]
    names = [blk[0] for _, blk in carriers]
    n = len(names)
    out = []
    for i, blk in blocks:
        tagged, k = [], 0
        while k < len(blk):
            tagged.append(blk[k])
            if blk[k].lower().endswith("prices") and n >= 3 and len(blk[k + 1:k + 1 + n]) == n:
                tagged += [f"[{names[j]}] {blk[k + 1 + j]}" for j in range(n)]
                k += n
            k += 1
        out.append((i, " ".join(tagged)))
    return out


def passages_from_text(text: str, query: str, k: int = 4, max_chars: int = 560) -> list[dict]:
    """Quotable, VERBATIM passages. Plan blocks (heading + its prices and rules) are preferred; when the page has no such
    structure, sliding windows of up to 3 lines are used. Scored by query-term overlap with a bonus for prices and minutes."""
    lines = text.split("\n")
    wanted = _tokens(query)
    candidates = [(i, txt[:max_chars], 0.4) for i, txt in _annotate_columns(_blocks(lines))]
    candidates += [(i, " ".join(lines[i:i + 3])[:max_chars], 0.0) for i in range(len(lines))]
    scored = []
    for i, passage, block_bonus in candidates:
        overlap = len(wanted & _tokens(passage))
        bonus = 0.5 * bool(re.search(r"\$\d", passage)) + 0.3 * bool(re.search(r"\bmin", passage, re.I)) + block_bonus
        if overlap:
            scored.append((overlap + bonus, i, passage))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen, used = [], set()
    for score, i, passage in scored:
        if any(abs(i - j) < 4 for j in used):
            continue
        used.add(i)
        chosen.append((score, passage))
        if len(chosen) == k:
            break
    return [{"text": w, "score": round(s, 2)} for s, w in chosen]


def policy_retriever(url: str, query: str, k: int = 4, snapshots: list | None = None) -> dict:
    """Fetch the pricing page, extract its text and return short quotable passages. The exact extracted text, the URL, the access
    time and its SHA-256 are appended to `snapshots` so a later change of the public page cannot change the evidence."""
    try:
        html, how = fetch_page(url)
    except (requests.RequestException, OSError) as exc:
        return envelope(False, error=f"could not fetch {url}: {exc}", source=url)
    text = extract_text(html)
    if snapshots is not None:
        snapshots.append({"url": url, "accessed_at": now_iso(), "fetched_via": how, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                          "raw_html_sha256": hashlib.sha256(html.encode()).hexdigest(), "chars": len(text), "text": text})
    found = passages_from_text(text, query, k)
    for p in found:
        p["source"] = url
    return envelope(True, {"passages": found}, source=url)


# --- calculator -------------------------------------------------------------------------------

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


def calculator(expression: str, units: str | None = None) -> dict:
    """Safe arithmetic: whitelist ^[0-9+\\-*/().\\s]+$, then a tiny AST evaluator (no eval)."""
    if not isinstance(expression, str) or not CALC_WHITELIST.match(expression):
        return envelope(False, error="expression may only contain digits, + - * / ( ) . and spaces")
    try:
        value = _eval(ast.parse(expression.strip(), mode="eval"))
    except ZeroDivisionError:
        return envelope(False, error="division by zero")
    except (SyntaxError, ValueError, RecursionError):
        return envelope(False, error="could not evaluate the expression")
    data = {"value": round(float(value), 6)}
    if units:
        data["units"] = units
    return envelope(True, data)
