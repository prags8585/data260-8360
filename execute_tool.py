"""HW5 Part 4/5: the single safe entry point the agent uses for every tool call.

    execute_tool(name, inputs, repo=None) -> JSON string of {"ok", "data", "error"}

Reuses the envelope from Part 2B. It never raises: unknown tools, bad inputs,
storage failures and safety-rule violations all come back as
{"ok": false, "data": null, "error": "..."}.

Part 5 safety rule (SENSITIVE_DATA_RULE): this is a course-catalogue and
enrolment assistant, so a search that asks for private personal data
(passwords, SSNs, payment cards, phone numbers, ...) is refused before it
reaches storage -- the catalogue holds none of it, and an agent must not be
nudged into hunting for it.
"""

import json
import logging
import re
from typing import Any

import domain_tools
from domain_tools import CourseRepo, fail

log = logging.getLogger("execute_tool")

SENSITIVE_TERMS = (
    "password", "passwd", "ssn", "social security", "credit card",
    "phone number", "home address", "date of birth", "bank account",
)
_SENSITIVE_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in SENSITIVE_TERMS) + r")\b", re.IGNORECASE)
BLOCK_PREFIX = "blocked by safety rule"


def check_safety(name: str, inputs: dict) -> str | None:
    """Returns an error message if the call violates the safety rule, else None."""
    if name == "search_courses":
        query = inputs.get("query")
        if isinstance(query, str):
            match = _SENSITIVE_RE.search(query)
            if match:
                return (f"{BLOCK_PREFIX} (sensitive-data): the query asks for '{match.group(0).lower()}', "
                        "which is private personal data and is not available through the course catalogue")
    return None


def execute_tool(name: Any, inputs: Any, repo: CourseRepo | None = None) -> str:
    try:
        tool = domain_tools.TOOLS.get(name) if isinstance(name, str) else None
        if tool is None:
            result = fail(f"unknown tool {name!r}; available tools: {', '.join(domain_tools.TOOLS)}")
        elif not isinstance(inputs, dict):
            result = fail("inputs must be a JSON object")
        else:
            blocked = check_safety(name, inputs)
            if blocked:
                log.warning("blocked %s %s: %s", name, inputs, blocked)
                result = fail(blocked)
            else:
                result = tool(repo if repo is not None else _default_repo(), **inputs)
    except TypeError as exc:  # missing / unexpected argument names
        result = fail(f"invalid arguments for {name}: {exc}")
    except Exception as exc:  # last-resort guard: execute_tool never raises
        log.exception("execute_tool crashed")
        result = fail(f"internal error: {type(exc).__name__}: {exc}")
    return json.dumps(result)


_repo_singleton: CourseRepo | None = None


def _default_repo() -> CourseRepo:
    global _repo_singleton
    if _repo_singleton is None:
        _repo_singleton = domain_tools.default_repo()
    return _repo_singleton
